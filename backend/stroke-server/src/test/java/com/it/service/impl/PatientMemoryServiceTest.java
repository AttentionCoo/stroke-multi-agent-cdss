package com.it.service.impl;

import com.it.mapper.AiOpinionMapper;
import com.it.mapper.HealthDataMapper;
import com.it.mapper.PatientMapper;
import com.it.mapper.TalkMapper;
import com.it.pojo.AiOpinion;
import com.it.pojo.HealthData;
import com.it.pojo.Patient;
import com.it.pojo.Talk;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PatientMemoryServiceTest {

    @Mock
    private PatientMapper patientMapper;
    @Mock
    private HealthDataMapper healthDataMapper;
    @Mock
    private AiOpinionMapper aiOpinionMapper;
    @Mock
    private TalkMapper talkMapper;
    private PatientMemoryService service;

    @BeforeEach
    void setUp() {
        service = new PatientMemoryService(
                patientMapper,
                healthDataMapper,
                aiOpinionMapper,
                talkMapper
        );
    }

    @Test
    void shouldBuildThreeLevelMemoryForOwnedPatient() {
        Patient patient = new Patient();
        patient.setId(7L);
        patient.setDoctorId(3L);
        patient.setHistory("高血压10年");
        patient.setNotes("长期服用华法林");

        HealthData healthData = new HealthData();
        healthData.setDataContent("血压 180/100 mmHg");

        AiOpinion opinion = new AiOpinion();
        opinion.setRiskLevel("高风险");
        opinion.setAnalysisDetails("既往评估提示卒中高风险");

        when(patientMapper.selectById(7L)).thenReturn(patient);
        when(talkMapper.selectById(11L)).thenReturn(ownedTalk(7L));
        when(healthDataMapper.selectList(any())).thenReturn(List.of(healthData));
        when(aiOpinionMapper.selectList(any())).thenReturn(List.of(opinion));

        Map<String, String> memory = service.build(3L, 7L, 11L, "本轮对话内容");

        assertEquals("本轮对话内容", memory.get("short_term"));
        assertTrue(memory.get("episodic").contains("血压 180/100"));
        assertTrue(memory.get("episodic").contains("既往评估提示卒中高风险"));
        assertTrue(memory.get("semantic").contains("高血压10年"));
        assertTrue(memory.get("semantic").contains("长期服用华法林"));
    }

    @Test
    void shouldRejectPatientOwnedByAnotherDoctor() {
        Patient patient = new Patient();
        patient.setId(7L);
        patient.setDoctorId(99L);
        when(patientMapper.selectById(7L)).thenReturn(patient);

        assertThrows(
                PatientMemoryService.PatientContextException.class,
                () -> service.build(3L, 7L, 11L, "本轮对话内容")
        );
    }

    @Test
    void shouldRejectSwitchingPatientWithinTheSameTalk() {
        Patient patient = new Patient();
        patient.setId(7L);
        patient.setDoctorId(3L);
        when(patientMapper.selectById(7L)).thenReturn(patient);
        when(talkMapper.selectById(11L)).thenReturn(ownedTalk(8L));

        PatientMemoryService.PatientContextException error = assertThrows(
                PatientMemoryService.PatientContextException.class,
                () -> service.build(3L, 7L, 11L, "其他患者的对话内容")
        );

        assertTrue(error.getMessage().contains("已关联其他患者"));
    }

    @Test
    void shouldRecoverShortMemoryFromPersistentScope() {
        Patient patient = new Patient();
        patient.setId(7L);
        patient.setDoctorId(3L);
        when(patientMapper.selectById(7L)).thenReturn(patient);
        when(talkMapper.selectById(11L)).thenReturn(ownedTalk(7L));
        when(healthDataMapper.selectList(any())).thenReturn(List.of());
        when(aiOpinionMapper.selectList(any())).thenReturn(List.of());

        Map<String, String> memory = service.build(3L, 7L, 11L, "缓存过期后的历史对话");

        assertEquals("缓存过期后的历史对话", memory.get("short_term"));
    }

    @Test
    void shouldPersistentlyBindAnEmptyTalkToPatient() {
        Patient patient = new Patient();
        patient.setId(7L);
        patient.setDoctorId(3L);
        when(patientMapper.selectById(7L)).thenReturn(patient);
        when(talkMapper.selectById(11L)).thenReturn(ownedTalk(null));
        when(talkMapper.update(isNull(), any())).thenReturn(1);
        when(healthDataMapper.selectList(any())).thenReturn(List.of());
        when(aiOpinionMapper.selectList(any())).thenReturn(List.of());

        Map<String, String> memory = service.build(3L, 7L, 11L, "");

        assertEquals("", memory.get("short_term"));
    }

    private Talk ownedTalk(Long patientId) {
        return Talk.builder()
                .id(11L)
                .userId(3L)
                .patientId(patientId)
                .title("测试对话")
                .content("")
                .build();
    }
}
