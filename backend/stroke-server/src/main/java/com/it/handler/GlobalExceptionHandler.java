package com.it.handler;

import com.it.domain.stroke.AssessmentConflictException;
import com.it.domain.stroke.AssessmentNotFoundException;
import com.it.domain.stroke.InvalidAssessmentReviewException;
import com.it.pojo.Result;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.sql.SQLIntegrityConstraintViolationException;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler({
            AssessmentNotFoundException.class,
            AssessmentConflictException.class,
            InvalidAssessmentReviewException.class
    })
    public Result strokeAssessmentExceptionHandler(RuntimeException ex) {
        return Result.error(ex.getMessage());
    }

    @ExceptionHandler
    public Result exceptionHandler(SQLIntegrityConstraintViolationException ex){
        String msgs =ex.getMessage();
        if(msgs.contains("Duplicate entry")){
            String[] split = msgs.split(" ");
            String username = split[2];
            String mg = username+ "已存在";
            return Result.error(mg);
        }
        else{
            return Result.error("未知错误");
        }
    }

}
