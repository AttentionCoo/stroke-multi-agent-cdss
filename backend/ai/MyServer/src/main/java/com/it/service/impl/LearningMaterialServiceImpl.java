package com.it.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.mapper.LearningMaterialMapper;
import com.it.po.vo.LearningMaterialDetailVO;
import com.it.po.vo.LearningMaterialPageVO;
import com.it.po.vo.LearningMaterialVO;
import com.it.pojo.LearningMaterial;
import com.it.pojo.Result;
import com.it.service.ILearningMaterialService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Slf4j
public class LearningMaterialServiceImpl
        extends ServiceImpl<LearningMaterialMapper, LearningMaterial>
        implements ILearningMaterialService {

    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 学习资料列表缓存 TTL（分钟） */
    private static final long LIST_TTL_MINUTES = 30;
    /** 学习资料详情缓存 TTL（分钟） */
    private static final long DETAIL_TTL_MINUTES = 60;

    @Override
    public Result getPage(String category, int page, int size) {
        String cacheKey = "material:page:" + (category != null ? category : "all") + ":" + page + ":" + size;

        // 尝试从 Redis 读取缓存
        try {
            String cached = stringRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null && !cached.isEmpty()) {
                log.debug("学习资料分页缓存命中: key={}", cacheKey);
                return Result.success(objectMapper.readValue(cached, LearningMaterialPageVO.class));
            }
        } catch (Exception e) {
            log.warn("读取学习资料分页缓存失败，降级查询DB: key={}", cacheKey, e.getMessage());
        }

        LambdaQueryWrapper<LearningMaterial> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(category)) {
            wrapper.eq(LearningMaterial::getCategory, category);
        }
        wrapper.orderByDesc(LearningMaterial::getCreateTime);

        Page<LearningMaterial> pageResult = this.page(new Page<>(page, size), wrapper);

        List<LearningMaterialVO> vos = pageResult.getRecords().stream().map(m -> {
            LearningMaterialVO vo = new LearningMaterialVO();
            vo.setId(m.getId());
            vo.setTitle(m.getTitle());
            vo.setType(m.getType());
            vo.setUrl(m.getUrl());
            return vo;
        }).toList();

        LearningMaterialPageVO pageVO = new LearningMaterialPageVO();
        pageVO.setTotal(pageResult.getTotal());
        pageVO.setMaterials(vos);

        // 写入 Redis 缓存
        try {
            stringRedisTemplate.opsForValue().set(cacheKey, objectMapper.writeValueAsString(pageVO),
                    LIST_TTL_MINUTES, TimeUnit.MINUTES);
            log.debug("学习资料分页缓存已写入: key={}", cacheKey);
        } catch (Exception e) {
            log.warn("写入学习资料分页缓存失败: key={}", cacheKey, e.getMessage());
        }

        return Result.success(pageVO);
    }

    @Override
    public Result getDetail(Long id) {
        String cacheKey = "material:detail:" + id;

        // 尝试从 Redis 读取缓存
        try {
            String cached = stringRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null && !cached.isEmpty()) {
                log.debug("学习资料详情缓存命中: key={}", cacheKey);
                return Result.success(objectMapper.readValue(cached, LearningMaterialDetailVO.class));
            }
        } catch (Exception e) {
            log.warn("读取学习资料详情缓存失败，降级查询DB: key={}", cacheKey, e.getMessage());
        }

        LearningMaterial m = this.getById(id);
        if (m == null) {
            return Result.error("资料不存在");
        }
        LearningMaterialDetailVO vo = new LearningMaterialDetailVO();
        vo.setId(m.getId());
        vo.setTitle(m.getTitle());
        vo.setContent(m.getContent());

        // 写入 Redis 缓存
        try {
            stringRedisTemplate.opsForValue().set(cacheKey, objectMapper.writeValueAsString(vo),
                    DETAIL_TTL_MINUTES, TimeUnit.MINUTES);
            log.debug("学习资料详情缓存已写入: key={}", cacheKey);
        } catch (Exception e) {
            log.warn("写入学习资料详情缓存失败: key={}", cacheKey, e.getMessage());
        }

        return Result.success(vo);
    }
}
