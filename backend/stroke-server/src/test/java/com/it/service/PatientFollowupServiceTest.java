package com.it.service;

import com.it.mapper.PatientFollowupMapper;
import com.it.mapper.PatientMapper;
import com.it.po.uo.PatientFollowupParam;
import com.it.pojo.Patient;
import com.it.pojo.PatientFollowup;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class PatientFollowupServiceTest {

    @Test
    void completeShouldRejectMrsOutsideZeroToSix() {
        PatientFollowupMapper followupMapper = mock(PatientFollowupMapper.class);
        PatientMapper patientMapper = mock(PatientMapper.class);
        Patient patient = new Patient();
        patient.setId(5L);
        patient.setDoctorId(3L);
        when(patientMapper.selectById(5L)).thenReturn(patient);

        PatientFollowup followup = new PatientFollowup();
        followup.setId(21L);
        followup.setDoctorId(3L);
        followup.setPatientId(5L);
        followup.setStatus("PENDING");
        when(followupMapper.selectById(21L)).thenReturn(followup);

        PatientFollowupService service = new PatientFollowupService(followupMapper, patientMapper);
        PatientFollowupParam param = new PatientFollowupParam();
        param.setPlannedDate(LocalDate.now());
        param.setMrsScore(7);

        assertThrows(IllegalArgumentException.class,
                () -> service.complete(3L, 5L, 21L, param));
    }
}
