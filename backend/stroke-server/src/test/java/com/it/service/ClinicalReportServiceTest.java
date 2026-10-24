package com.it.service;

import com.it.mapper.ClinicalReportMapper;
import com.it.mapper.TalkMapper;
import com.it.po.uo.ClinicalReportParam;
import com.it.pojo.ClinicalReport;
import com.it.pojo.Talk;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ClinicalReportServiceTest {

    @Test
    void saveDraftShouldPersistVersionedReportForOwnedTalk() {
        ClinicalReportMapper reportMapper = mock(ClinicalReportMapper.class);
        TalkMapper talkMapper = mock(TalkMapper.class);
        when(talkMapper.selectById(11L)).thenReturn(Talk.builder().id(11L).userId(3L).build());
        when(reportMapper.selectOne(any())).thenReturn(null);
        ClinicalReportService service = new ClinicalReportService(reportMapper, talkMapper);

        ClinicalReportParam param = new ClinicalReportParam();
        param.setTalkId(11L);
        param.setMessageIndex(2);
        param.setTitle("卒中报告");
        param.setOriginalContent("AI 原稿");
        param.setContent("医生修改稿");

        service.saveDraft(3L, param);

        ArgumentCaptor<ClinicalReport> captor = ArgumentCaptor.forClass(ClinicalReport.class);
        verify(reportMapper).insert(captor.capture());
        assertEquals(3L, captor.getValue().getDoctorId());
        assertEquals(1, captor.getValue().getVersion());
        assertEquals("DRAFT", captor.getValue().getStatus());
        assertEquals("AI 原稿", captor.getValue().getOriginalContent());
        assertEquals("医生修改稿", captor.getValue().getContent());
    }

    @Test
    void signShouldRequireSignature() {
        ClinicalReportService service = new ClinicalReportService(
                mock(ClinicalReportMapper.class), mock(TalkMapper.class));
        assertThrows(IllegalArgumentException.class, () -> service.sign(3L, 1L, " "));
    }
}
