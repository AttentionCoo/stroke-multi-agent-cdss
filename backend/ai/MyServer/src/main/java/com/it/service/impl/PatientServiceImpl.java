package com.it.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.mapper.AiOpinionMapper;
import com.it.mapper.PatientMapper;
import com.it.po.uo.PatientParam;
import com.it.po.vo.AiOpinionVO;
import com.it.po.vo.PatientDetailVO;
import com.it.po.vo.PatientPageVO;
import com.it.po.vo.PatientVO;
import com.it.pojo.AiOpinion;
import com.it.pojo.Patient;
import com.it.pojo.Result;
import com.it.service.IPatientService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Service
@Transactional
@RequiredArgsConstructor
@Slf4j
public class PatientServiceImpl extends ServiceImpl<PatientMapper, Patient> implements IPatientService {

    private final AiOpinionMapper aiOpinionMapper;
    private final StringRedisTemplate stringRedisTemplate;

    /** 从 ThreadLocal 获取当前登录医生 ID */
    private Long currentDoctorId() {
        return ThreadLocalUtil.getCurrentUser().getId();
    }

    /**
     * 患者分页列表 —— Redis 缓存。
     * 缓存 key: patient:page:{doctorId}:{page}:{size}:{nameHash}:{diseasesHash}
     * 增删改时通过 @CacheEvict 清除该医生的所有分页缓存。
     */
    @Override
    public Result getPatientPage(int page, int size, String name, String diseases) {
        Long doctorId = currentDoctorId();
        String cacheKey = buildPatientPageKey(doctorId, page, size, name, diseases);

        // 尝试从 Redis 读取缓存
        try {
            String cached = stringRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null && !cached.isEmpty()) {
                log.debug("患者分页缓存命中: key={}", cacheKey);
                return Result.success(
                        new com.fasterxml.jackson.databind.ObjectMapper()
                            .readValue(cached, PatientPageVO.class));
            }
        } catch (Exception e) {
            log.warn("读取患者分页缓存失败，降级查询DB: key={}, err={}", cacheKey, e.getMessage());
        }

        // 缓存未命中，查询数据库
        LambdaQueryWrapper<Patient> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Patient::getDoctorId, doctorId);
        if (StringUtils.hasText(name)) {
            wrapper.like(Patient::getName, name);
        }
        if (StringUtils.hasText(diseases)) {
            wrapper.like(Patient::getHistory, diseases);
        }
        wrapper.orderByDesc(Patient::getUpdateTime);

        Page<Patient> pageResult = this.page(new Page<>(page, size), wrapper);
        List<Patient> records = pageResult.getRecords();

        List<PatientVO> patientVOs = new ArrayList<>(records.size());
        for (Patient patient : records) {
            PatientVO vo = new PatientVO();
            vo.setId(patient.getId());
            vo.setName(patient.getName());
            vo.setHistory(patient.getHistory());
            vo.setNotes(patient.getNotes());

            AiOpinion opinion = aiOpinionMapper.selectLatestByPatientId(patient.getId());
            if (opinion != null) {
                StringBuilder sb = new StringBuilder();
                if (StringUtils.hasText(opinion.getSuggestions())) {
                    sb.append(opinion.getSuggestions());
                }
                if (StringUtils.hasText(opinion.getRiskLevel())) {
                    if (sb.length() > 0) sb.append("，");
                    sb.append("风险等级：").append(opinion.getRiskLevel());
                }
                if (sb.length() > 0) {
                    vo.setAiOpinion(sb.toString());
                }
            }
            patientVOs.add(vo);
        }

        PatientPageVO pageVO = new PatientPageVO();
        pageVO.setTotal(pageResult.getTotal());
        pageVO.setPatients(patientVOs);

        // 写入 Redis 缓存（5 分钟 TTL）
        try {
            com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
            stringRedisTemplate.opsForValue().set(cacheKey, om.writeValueAsString(pageVO), 5, TimeUnit.MINUTES);
            log.debug("患者分页缓存已写入: key={}", cacheKey);
        } catch (Exception e) {
            log.warn("写入患者分页缓存失败: key={}, err={}", cacheKey, e.getMessage());
        }

        return Result.success(pageVO);
    }

    @Override
    @CacheEvict(value = "patient", allEntries = true)
    public Result addPatient(PatientParam param) {
        Long doctorId = currentDoctorId();

        Patient patient = new Patient();
        patient.setName(param.getName());
        patient.setHistory(param.getHistory());
        patient.setNotes(param.getNotes());
        patient.setDoctorId(doctorId);
        this.save(patient);

        // 清除该医生的分页缓存
        evictDoctorPatientCaches(doctorId);

        return Result.success(Map.of("id", patient.getId()));
    }

    @Override
    @CacheEvict(value = "patient", allEntries = true)
    public Result updatePatient(Long id, PatientParam param) {
        Long doctorId = currentDoctorId();
        Patient patient = this.getById(id);
        if (patient == null || !doctorId.equals(patient.getDoctorId())) {
            return Result.error("病人不存在或无权限");
        }

        patient.setName(param.getName());
        patient.setHistory(param.getHistory());
        patient.setNotes(param.getNotes());
        this.updateById(patient);

        // 清除该医生的分页缓存 + 该患者的详情缓存
        evictDoctorPatientCaches(doctorId);
        evictPatientDetailCache(id);

        return Result.success();
    }

    @Override
    @CacheEvict(value = "patient", allEntries = true)
    public Result deletePatient(Long id) {
        Long doctorId = currentDoctorId();
        Patient patient = this.getById(id);
        if (patient == null || !doctorId.equals(patient.getDoctorId())) {
            return Result.error("病人不存在或无权限");
        }

        // 先删关联的 AI 分析记录，避免外键约束报错
        LambdaQueryWrapper<AiOpinion> opWrapper = new LambdaQueryWrapper<>();
        opWrapper.eq(AiOpinion::getPatientId, id);
        aiOpinionMapper.delete(opWrapper);

        this.removeById(id);

        // 清除缓存
        evictDoctorPatientCaches(doctorId);
        evictPatientDetailCache(id);

        return Result.success();
    }

    @Override
    public Result getPatientDetail(Long id) {
        Long doctorId = currentDoctorId();

        String detailKey = "patient:detail:" + id;
        // 尝试从 Redis 读取
        try {
            String cached = stringRedisTemplate.opsForValue().get(detailKey);
            if (cached != null && !cached.isEmpty()) {
                log.debug("患者详情缓存命中: key={}", detailKey);
                return Result.success(
                        new com.fasterxml.jackson.databind.ObjectMapper()
                            .readValue(cached, PatientDetailVO.class));
            }
        } catch (Exception e) {
            log.warn("读取患者详情缓存失败，降级查询DB: key={}", detailKey, e.getMessage());
        }

        Patient patient = this.getById(id);
        if (patient == null || !doctorId.equals(patient.getDoctorId())) {
            return Result.error("病人不存在或无权限");
        }

        PatientDetailVO vo = new PatientDetailVO();
        vo.setId(patient.getId());
        vo.setName(patient.getName());
        vo.setHistory(patient.getHistory());
        vo.setNotes(patient.getNotes());

        AiOpinion opinion = aiOpinionMapper.selectLatestByPatientId(id);
        if (opinion != null) {
            AiOpinionVO opVO = new AiOpinionVO();
            opVO.setRiskLevel(opinion.getRiskLevel());
            opVO.setSuggestion(opinion.getSuggestions());
            opVO.setAnalysisDetails(opinion.getAnalysisDetails());
            opVO.setLastUpdatedAt(opinion.getUpdateTime());
            vo.setAiOpinion(opVO);
        }

        // 写入 Redis 缓存（10 分钟 TTL）
        try {
            com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
            stringRedisTemplate.opsForValue().set(detailKey, om.writeValueAsString(vo), 10, TimeUnit.MINUTES);
            log.debug("患者详情缓存已写入: key={}", detailKey);
        } catch (Exception e) {
            log.warn("写入患者详情缓存失败: key={}", detailKey, e.getMessage());
        }

        return Result.success(vo);
    }

    // ── 缓存清除辅助方法 ───────────────────────────────────────────────────────

    /** 清除某医生的所有分页缓存（模糊匹配删除） */
    private void evictDoctorPatientCaches(Long doctorId) {
        try {
            String pattern = "patient:page:" + doctorId + ":*";
            var keys = stringRedisTemplate.keys(pattern);
            if (keys != null && !keys.isEmpty()) {
                stringRedisTemplate.delete(keys);
                log.debug("已清除医生患者分页缓存: doctorId={}, count={}", doctorId, keys.size());
            }
        } catch (Exception e) {
            log.warn("清除患者分页缓存失败: doctorId={}, err={}", doctorId, e.getMessage());
        }
    }

    /** 清除单个患者详情缓存 */
    private void evictPatientDetailCache(Long patientId) {
        try {
            stringRedisTemplate.delete("patient:detail:" + patientId);
            log.debug("已清除患者详情缓存: patientId={}", patientId);
        } catch (Exception e) {
            log.warn("清除患者详情缓存失败: patientId={}", patientId, e.getMessage());
        }
    }

    /** 构建患者分页缓存 key */
    private String buildPatientPageKey(Long doctorId, int page, int size, String name, String diseases) {
        int nameHash = (name != null ? name : "").hashCode();
        int disHash = (diseases != null ? diseases : "").hashCode();
        return "patient:page:" + doctorId + ":" + page + ":" + size + ":" + nameHash + ":" + disHash;
    }
}
