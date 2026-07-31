-- ============================================
-- medai 数据库完整建表脚本（修改后版本）
-- 包含所有表：user, talk, cont, patient, ai_opinion, learning_material, health_data
-- ============================================

CREATE DATABASE IF NOT EXISTS `medai` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE `medai`;

-- ----------------------------
-- Table: user
-- ----------------------------
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `name` varchar(15) COLLATE utf8mb4_general_ci NOT NULL COMMENT '用户名',
  `password` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '密码哈希值',
  `image` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '头像',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `update_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: talk
-- ----------------------------
DROP TABLE IF EXISTS `talk`;
CREATE TABLE `talk` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `title` text COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题',
  `content` text COLLATE utf8mb4_general_ci NOT NULL COMMENT '主要内容',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `update_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: cont
-- ----------------------------
DROP TABLE IF EXISTS `cont`;
CREATE TABLE `cont` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `talk_id` bigint unsigned NOT NULL,
  `content` text COLLATE utf8mb4_general_ci NOT NULL COMMENT '存储的内容',
  `role` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '消息角色：user 或 assistant',
  `images` text COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '用户上传图片的 Base64 列表，JSON 字符串存储',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: patient
-- ----------------------------
DROP TABLE IF EXISTS `patient`;
CREATE TABLE `patient` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '患者姓名',
  `history` text COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '病史',
  `notes` text COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注',
  `doctor_id` bigint unsigned NOT NULL COMMENT '负责医生ID',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `update_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: ai_opinion
-- ----------------------------
DROP TABLE IF EXISTS `ai_opinion`;
CREATE TABLE `ai_opinion` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `patient_id` bigint unsigned NOT NULL COMMENT '患者ID',
  `risk_level` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '风险等级：低/中/高',
  `suggestions` text COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'AI建议',
  `analysis_details` text COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '分析详情',
  `source_type` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源类型：health_data / sync_talk',
  `source_id` bigint unsigned DEFAULT NULL COMMENT '来源ID',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `update_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_patient_id` (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: learning_material
-- ----------------------------
DROP TABLE IF EXISTS `learning_material`;
CREATE TABLE `learning_material` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `title` varchar(200) COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题',
  `category` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '分类',
  `type` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '类型：文档/视频/链接',
  `url` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '资源URL',
  `content` longtext COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '内容',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `update_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: health_data
-- ----------------------------
DROP TABLE IF EXISTS `health_data`;
CREATE TABLE `health_data` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `patient_id` bigint unsigned NOT NULL COMMENT '患者ID',
  `data_content` text COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '健康数据JSON',
  `create_time` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_patient_id` (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table: stroke_assessment
-- ----------------------------
DROP TABLE IF EXISTS `stroke_assessment_review`;
DROP TABLE IF EXISTS `stroke_assessment`;
CREATE TABLE `stroke_assessment` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `doctor_id` bigint unsigned NOT NULL COMMENT '负责医生ID',
  `patient_id` bigint unsigned DEFAULT NULL COMMENT '关联患者ID',
  `last_known_well_at` datetime DEFAULT NULL COMMENT '最后正常时间',
  `arrival_at` datetime DEFAULT NULL COMMENT '到院时间',
  `systolic_blood_pressure` int DEFAULT NULL COMMENT '收缩压 mmHg',
  `diastolic_blood_pressure` int DEFAULT NULL COMMENT '舒张压 mmHg',
  `blood_glucose_mmol_l` decimal(6,2) DEFAULT NULL COMMENT '血糖 mmol/L',
  `nihss_score` int DEFAULT NULL COMMENT 'NIHSS总分',
  `platelet_count` int DEFAULT NULL COMMENT '血小板计数 ×10^9/L',
  `inr` decimal(5,2) DEFAULT NULL COMMENT '国际标准化比值',
  `anticoagulant_use` varchar(16) NOT NULL DEFAULT 'UNKNOWN' COMMENT 'YES/NO/UNKNOWN',
  `anticoagulant_last_dose_at` datetime DEFAULT NULL COMMENT '抗凝药末次用药时间',
  `ct_hemorrhage` varchar(16) NOT NULL DEFAULT 'UNKNOWN' COMMENT 'YES/NO/UNKNOWN',
  `cta_large_vessel_occlusion` varchar(16) NOT NULL DEFAULT 'UNKNOWN' COMMENT 'YES/NO/UNKNOWN',
  `notes` text COMMENT '补充信息',
  `version` int NOT NULL DEFAULT 1 COMMENT '乐观版本号',
  `status` varchar(24) NOT NULL DEFAULT 'DRAFT' COMMENT '审核状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_stroke_assessment_doctor_time` (`doctor_id`, `update_time`),
  KEY `idx_stroke_assessment_patient` (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='脑卒中急诊结构化评估';

-- ----------------------------
-- Table: stroke_assessment_review
-- ----------------------------
CREATE TABLE `stroke_assessment_review` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `assessment_id` bigint unsigned NOT NULL,
  `doctor_id` bigint unsigned NOT NULL,
  `action` varchar(24) NOT NULL COMMENT 'ACCEPT/REQUEST_EDIT/REJECT',
  `reason` varchar(1000) DEFAULT NULL,
  `assessment_version` int NOT NULL,
  `assessment_snapshot` longtext NOT NULL COMMENT '审核时的结构化评估快照',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_stroke_review_assessment_time` (`assessment_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='脑卒中评估审核审计记录';
