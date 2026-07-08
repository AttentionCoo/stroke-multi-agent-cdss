package com.it;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.ServletComponentScan;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@ServletComponentScan
@MapperScan("com.it.mapper")
@SpringBootApplication
public class StrokeServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(StrokeServerApplication.class, args);
    }
}
