package com.it.service;

import com.it.mapper.DoctorFeedbackMapper;
import com.it.mapper.TalkMapper;
import com.it.po.uo.DoctorFeedbackParam;
import com.it.pojo.DoctorFeedback;
import com.it.pojo.Talk;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DoctorFeedbackServiceTest {

    @Test
    void submitShouldPersistFeedbackForOwnedTalk() {
        DoctorFeedbackMapper feedbackMapper = mock(DoctorFeedbackMapper.class);
        TalkMapper talkMapper = mock(TalkMapper.class);
        when(talkMapper.selectById(12L)).thenReturn(Talk.builder().id(12L).userId(3L).build());
        DoctorFeedbackService service = new DoctorFeedbackService(feedbackMapper, talkMapper);

        DoctorFeedbackParam param = new DoctorFeedbackParam();
        param.setTalkId(12L);
        param.setRating(-1);
        param.setCategory("证据支持不足");
        param.setComment("引用页码不一致");

        service.submit(3L, param);

        ArgumentCaptor<DoctorFeedback> captor = ArgumentCaptor.forClass(DoctorFeedback.class);
        verify(feedbackMapper).insert(captor.capture());
        assertEquals(3L, captor.getValue().getDoctorId());
        assertEquals(-1, captor.getValue().getRating());
        assertEquals("证据支持不足", captor.getValue().getCategory());
    }

    @Test
    void submitShouldRejectInvalidRating() {
        DoctorFeedbackService service = new DoctorFeedbackService(
                mock(DoctorFeedbackMapper.class), mock(TalkMapper.class));
        DoctorFeedbackParam param = new DoctorFeedbackParam();
        param.setTalkId(12L);
        param.setRating(0);

        assertThrows(IllegalArgumentException.class, () -> service.submit(3L, param));
    }
}
