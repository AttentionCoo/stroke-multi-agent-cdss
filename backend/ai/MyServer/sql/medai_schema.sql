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