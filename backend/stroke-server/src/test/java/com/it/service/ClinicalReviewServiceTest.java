package com.it.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.mapper.ClinicalReviewTaskMapper;
import com.it.mapper.TalkMapper;
import com.it.pojo.ClinicalReviewTask;
import com.it.pojo.Talk;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ClinicalReviewServiceTest {

    @Test
    void createPendingShouldPersistTaskForTalkOwner() throws Exception {
        ClinicalReviewTaskMapper taskMapper = mock(ClinicalReviewTaskMapper.class);
        TalkMapper talkMapper = mock(TalkMapper.class);
        when(talkMapper.selectById(88L)).thenReturn(Talk.builder().id(88L).userId(7L).build());
        when(taskMapper.selectOne(any())).thenReturn(null);

        ClinicalReviewService service = new ClinicalReviewService(
                taskMapper, talkMapper, new ObjectMapper());
        var payload = new ObjectMapper().readTree("{\"consensus\":\"test\"}");

        Optional<ClinicalReviewTask> task = service.createOrUpdatePending(88L, "thread-1", payload);

        assertTrue(task.isPresent());
        ArgumentCaptor<ClinicalReviewTask> captor = ArgumentCaptor.forClass(ClinicalReviewTask.class);
        verify(taskMapper).insert(captor.capture());
        assertEquals(7L, captor.getValue().getDoctorId());
        assertEquals("PENDING", captor.getValue().getStatus());
        assertTrue(captor.getValue().getPayloadJson().contains("consensus"));
    }

    @Test
    void pendingLookupShouldRejectTalkOfAnotherDoctor() {
        ClinicalReviewTaskMapper taskMapper = mock(ClinicalReviewTaskMapper.class);
        TalkMapper talkMapper = mock(TalkMapper.class);
        when(talkMapper.selectById(88L)).thenReturn(Talk.builder().id(88L).userId(9L).build());
        ClinicalReviewService service = new ClinicalReviewService(taskMapper, talkMapper, new ObjectMapper());

        assertFalse(service.findPendingByTalk(7L, 88L).isPresent());
    }
}
