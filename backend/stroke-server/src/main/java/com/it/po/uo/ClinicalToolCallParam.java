package com.it.po.uo;

import lombok.Data;

import java.util.HashMap;
import java.util.Map;

/** 临床工具调用请求体。 */
@Data
public class ClinicalToolCallParam {
    private String name;
    private Map<String, Object> arguments = new HashMap<>();
}
