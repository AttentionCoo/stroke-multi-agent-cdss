package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.it.mapper.ClinicalReportMapper;
import com.it.mapper.TalkMapper;
import com.it.po.uo.ClinicalReportParam;
import com.it.pojo.ClinicalReport;
import com.it.pojo.Talk;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;

/** AI 报告草稿、编辑版本与医生签署。 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ClinicalReportService {

    private final ClinicalReportMapper reportMapper;
    private final TalkMapper talkMapper;

    @Transactional
    public ClinicalReport saveDraft(Long doctorId, ClinicalReportParam param) {
        if (param == null || param.getTalkId() == null || param.getMessageIndex() == null) {
            throw new IllegalArgumentException("talkId 与 messageIndex 不能为空");
        }
        if (!StringUtils.hasText(param.getContent())) {
            throw new IllegalArgumentException("报告内容不能为空");
        }
        verifyTalkOwner(doctorId, param.getTalkId());

        ClinicalReport existing = reportMapper.selectOne(new LambdaQueryWrapper<ClinicalReport>()
                .eq(ClinicalReport::getDoctorId, doctorId)
                .eq(ClinicalReport::getTalkId, param.getTalkId())
                .eq(ClinicalReport::getMessageIndex, param.getMessageIndex())
                .last("LIMIT 1"));

        LocalDateTime now = LocalDateTime.now();
        ClinicalReport report = existing == null ? new ClinicalReport() : existing;
        if (existing == null) {
            report.setDoctorId(doctorId);
            report.setTalkId(param.getTalkId());
            report.setMessageIndex(param.getMessageIndex());
            report.setVersion(1);
            report.setStatus("DRAFT");
            report.setCreateTime(now);
            report.setOriginalContent(StringUtils.hasText(param.getOriginalContent())
                    ? param.getOriginalContent() : param.getContent());
        } else {
            report.setVersion((report.getVersion() == null ? 1 : report.getVersion()) + 1);
            report.setStatus("DRAFT");
            report.setSignature(null);
            report.setSignedAt(null);
        }
        report.setTitle(normalizeTitle(param.getTitle()));
        report.setContent(param.getContent());
        report.setUpdateTime(now);
        if (existing == null) {
            reportMapper.insert(report);
        } else {
            reportMapper.updateById(report);
        }
        log.info("保存 AI 报告草稿: doctorId={}, talkId={}, messageIndex={}, version={}",
                doctorId, param.getTalkId(), param.getMessageIndex(), report.getVersion());
        return report;
    }

    public List<ClinicalReport> listByTalk(Long doctorId, Long talkId) {
        verifyTalkOwner(doctorId, talkId);
        return reportMapper.selectList(new LambdaQueryWrapper<ClinicalReport>()
                .eq(ClinicalReport::getDoctorId, doctorId)
                .eq(ClinicalReport::getTalkId, talkId)
                .orderByDesc(ClinicalReport::getUpdateTime));
    }

    public ClinicalReport getOwned(Long doctorId, Long reportId) {
        ClinicalReport report = reportMapper.selectById(reportId);
        if (report == null || !doctorId.equals(report.getDoctorId())) {
            throw new IllegalArgumentException("报告不存在或无权限");
        }
        return report;
    }

    @Transactional
    public ClinicalReport sign(Long doctorId, Long reportId, String signature) {
        if (!StringUtils.hasText(signature)) {
            throw new IllegalArgumentException("医生签名不能为空");
        }
        ClinicalReport report = getOwned(doctorId, reportId);
        report.setSignature(signature.trim());
        report.setStatus("SIGNED");
        report.setSignedAt(LocalDateTime.now());
        report.setUpdateTime(LocalDateTime.now());
        reportMapper.updateById(report);
        log.info("AI 报告已签署: doctorId={}, reportId={}, version={}", doctorId, reportId, report.getVersion());
        return report;
    }

    public long signedCount(Long doctorId) {
        Long count = reportMapper.selectCount(new LambdaQueryWrapper<ClinicalReport>()
                .eq(ClinicalReport::getDoctorId, doctorId)
                .eq(ClinicalReport::getStatus, "SIGNED"));
        return count == null ? 0 : count;
    }

    private void verifyTalkOwner(Long doctorId, Long talkId) {
        Talk talk = talkMapper.selectById(talkId);
        if (talk == null || !doctorId.equals(talk.getUserId())) {
            throw new IllegalArgumentException("对话不存在或无权限");
        }
    }

    private String normalizeTitle(String title) {
        if (!StringUtils.hasText(title)) return "临床辅助分析报告";
        String text = title.trim();
        return text.length() <= 255 ? text : text.substring(0, 255);
    }
}
