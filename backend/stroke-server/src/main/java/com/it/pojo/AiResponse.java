package com.it.pojo;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class AiResponse {

    @JsonProperty("result")
    private String result;   // AI 回答

    @JsonProperty("summary")
    private String summary;  // 历史总结

    @JsonProperty("name")
    private String name;     // 对话标题

    public static AiResponse fail(String msg) {
        AiResponse r = new AiResponse();
        r.setResult(msg);
        r.setSummary("");
        r.setName("AI 对话");
        return r;
    }
}

