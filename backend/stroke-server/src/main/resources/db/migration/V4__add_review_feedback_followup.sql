-- v2.11 升级: 医生复核任务、回答反馈、患者随访与纵向时间线所需数据表
-- 所有业务表均按 doctor_id 隔离, 由后端从当前登录用户写入与校验。

CREATE TABLE IF NOT EXISTS clinical_review_task (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doctor_id       BIGINT UNSIGNED NOT NULL COMMENT '负责医生ID',
    talk_id         BIGINT UNSIGNED NOT NULL COMMENT '关联对话ID',
    thread_id       VARCHAR(64)  NOT NULL COMMENT 'LangGraph 检查点线程ID',
    status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/COMPLETED/FAILED',
    payload_json    LONGTEXT     NULL COMMENT '待复核会诊摘要(共识/提案/风险)',
    decision        VARCHAR(20)  NULL COMMENT 'APPROVED/REJECTED',
    feedback        VARCHAR(2000) NULL COMMENT '医生驳回意见',
    answer          LONGTEXT     NULL COMMENT '复核通过后生成的最终报告',
    create_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_review_talk_thread (talk_id, thread_id),
    INDEX idx_review_doctor_status (doctor_id, status),
    INDEX idx_review_talk (talk_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI会诊医生复核任务';

CREATE TABLE IF NOT EXISTS doctor_feedback (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doctor_id       BIGINT UNSIGNED NOT NULL COMMENT '反馈医生ID',
    talk_id         BIGINT UNSIGNED NOT NULL COMMENT '关联对话ID',
    rating          TINYINT         NOT NULL COMMENT '1=有帮助, -1=需改进',
    category        VARCHAR(64)     NULL COMMENT '反馈分类',
    comment         VARCHAR(1000)   NULL COMMENT '医生补充说明',
    answer_excerpt  VARCHAR(4000)   NULL COMMENT '被反馈回答的摘要',
    create_time     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_feedback_doctor_time (doctor_id, create_time),
    INDEX idx_feedback_talk (talk_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI回答医生反馈';

CREATE TABLE IF NOT EXISTS patient_followup (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doctor_id       BIGINT UNSIGNED NOT NULL COMMENT '负责医生ID',
    patient_id      BIGINT UNSIGNED NOT NULL COMMENT '患者ID',
    planned_date    DATE            NOT NULL COMMENT '计划随访日期',
    followup_type   VARCHAR(32)     NOT NULL DEFAULT 'OUTPATIENT' COMMENT 'OUTPATIENT/PHONE/WECHAT/OTHER',
    status          VARCHAR(20)     NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/COMPLETED/CANCELLED',
    mrs_score       INT             NULL COMMENT 'mRS 0-6',
    recurrence      VARCHAR(16)     NULL COMMENT 'YES/NO/UNKNOWN',
    adherence       VARCHAR(16)     NULL COMMENT 'GOOD/PARTIAL/POOR/UNKNOWN',
    notes           TEXT            NULL COMMENT '随访记录与处置',
    completed_at    DATETIME        NULL,
    create_time     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_followup_patient_date (patient_id, planned_date),
    INDEX idx_followup_doctor_status (doctor_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='卒中患者随访任务与结局';
