ALTER TABLE talk
    ADD COLUMN thinking_json LONGTEXT NULL COMMENT '思考链历史(JSON数组: 每轮推理过程/专家意见/用量), 供刷新后重新打开思维链' AFTER content;
