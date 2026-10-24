-- v3 Web 工作台: AI 报告草稿/签署与版本化
CREATE TABLE IF NOT EXISTS clinical_report (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doctor_id         BIGINT UNSIGNED NOT NULL COMMENT '医生ID',
    talk_id           BIGINT UNSIGNED NOT NULL COMMENT '对话ID',
    message_index     INT NOT NULL COMMENT 'AI回答在对话中的下标, 用于快速定位',
    title             VARCHAR(255) NOT NULL DEFAULT '临床辅助分析报告',
    original_content  LONGTEXT NOT NULL COMMENT 'AI原始回答全文',
    content           LONGTEXT NOT NULL COMMENT '医生编辑后的报告全文',
    status            VARCHAR(20) NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT/SIGNED',
    signature         VARCHAR(100) NULL COMMENT '医生签名',
    version           INT NOT NULL DEFAULT 1,
    signed_at         DATETIME NULL,
    create_time       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_report_talk_message (doctor_id, talk_id, message_index),
    INDEX idx_report_doctor_time (doctor_id, update_time),
    INDEX idx_report_talk (talk_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI临床报告工作台';
