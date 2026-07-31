CREATE TABLE IF NOT EXISTS stroke_assessment (
    id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doctor_id                   BIGINT UNSIGNED NOT NULL,
    patient_id                  BIGINT UNSIGNED NULL,
    last_known_well_at          DATETIME NULL,
    arrival_at                  DATETIME NULL,
    systolic_blood_pressure     INT NULL,
    diastolic_blood_pressure    INT NULL,
    blood_glucose_mmol_l        DECIMAL(6,2) NULL,
    nihss_score                 INT NULL,
    platelet_count              INT NULL,
    inr                         DECIMAL(5,2) NULL,
    anticoagulant_use           VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN',
    anticoagulant_last_dose_at  DATETIME NULL,
    ct_hemorrhage               VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN',
    cta_large_vessel_occlusion  VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN',
    notes                       TEXT NULL,
    version                     INT NOT NULL DEFAULT 1,
    status                      VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    change_summary              TEXT NULL,
    create_time                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_stroke_assessment_doctor_time(doctor_id, update_time),
    INDEX idx_stroke_assessment_patient(patient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='脑卒中急诊结构化评估';

CREATE TABLE IF NOT EXISTS stroke_assessment_review (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    assessment_id       BIGINT UNSIGNED NOT NULL,
    doctor_id           BIGINT UNSIGNED NOT NULL,
    action              VARCHAR(24) NOT NULL,
    reason              VARCHAR(1000) NULL,
    assessment_version  INT NOT NULL,
    assessment_snapshot LONGTEXT NOT NULL,
    create_time         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_stroke_review_assessment_time(assessment_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='脑卒中评估审核审计记录';
