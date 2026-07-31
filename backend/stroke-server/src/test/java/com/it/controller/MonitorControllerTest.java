package com.it.controller;

import com.it.pojo.Result;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MonitorControllerTest {

    @Test
    void healthShouldReturnUpWithoutExternalDependencies() {
        MonitorController controller = new MonitorController(null, null);

        Result result = controller.health();

        assertEquals(1, result.getCode());
        assertEquals("success", result.getMsg());
        assertEquals("UP", ((Map<?, ?>) result.getData()).get("status"));
    }
}
