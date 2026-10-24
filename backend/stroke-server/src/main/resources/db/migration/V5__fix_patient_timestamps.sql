-- 修复旧版 patient 表时间字段类型不一致导致患者时间线缺失建档事件的问题。
-- 1) 先把可空/可能非法的字符串时间统一补齐为合法值；
-- 2) 再转换为 DATETIME 并增加默认值与更新时间自动维护。
UPDATE patient
SET create_time = DATE_FORMAT(COALESCE(create_time, NOW()), '%Y-%m-%d %H:%i:%s')
WHERE create_time IS NULL
   OR create_time = ''
   OR STR_TO_DATE(create_time, '%Y-%m-%d %H:%i:%s') IS NULL;

UPDATE patient
SET update_time = DATE_FORMAT(
        COALESCE(update_time, create_time, NOW()),
        '%Y-%m-%d %H:%i:%s'
    )
WHERE update_time IS NULL
   OR update_time = ''
   OR STR_TO_DATE(update_time, '%Y-%m-%d %H:%i:%s') IS NULL;

ALTER TABLE patient
    MODIFY COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    MODIFY COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
