package com.it.domain.stroke;

public class AssessmentNotFoundException extends RuntimeException {
    public AssessmentNotFoundException() {
        super("评估记录不存在或无权限");
    }
}
