package com.it.domain.stroke;

public class AssessmentConflictException extends RuntimeException {
    public AssessmentConflictException() {
        super("评估记录已被更新，请刷新后重试");
    }
}
