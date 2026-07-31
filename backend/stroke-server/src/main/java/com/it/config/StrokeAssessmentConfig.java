package com.it.config;

import com.it.domain.stroke.StrokeAssessmentModule;
import com.it.domain.stroke.StrokeAssessmentStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;
import java.time.ZoneId;

@Configuration
public class StrokeAssessmentConfig {

    @Bean
    public Clock applicationClock(@Value("${app.clinical-zone:Asia/Shanghai}") String clinicalZone) {
        return Clock.system(ZoneId.of(clinicalZone));
    }

    @Bean
    public StrokeAssessmentModule strokeAssessmentModule(StrokeAssessmentStore store, Clock applicationClock) {
        return new StrokeAssessmentModule(store, applicationClock);
    }
}
