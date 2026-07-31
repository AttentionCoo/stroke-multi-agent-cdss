ALTER TABLE talk
    ADD COLUMN patient_id BIGINT UNSIGNED NULL COMMENT '该对话绑定的患者ID' AFTER user_id,
    ADD INDEX idx_talk_patient_id (patient_id);
