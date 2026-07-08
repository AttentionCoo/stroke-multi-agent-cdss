package com.it.controller;

import com.it.po.uo.User;
import com.it.pojo.*;
import com.it.service.ILoginService;
import com.it.service.IRegiService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

@RestController
@CrossOrigin("*")
@RequestMapping("/api/user")
@Slf4j
@RequiredArgsConstructor
public class LoginController {

    private final IRegiService regiService;

    private final ILoginService loginService;

    @PostMapping("/register")
    public Result register(@RequestBody User user) {
        return regiService.insertUser(user);
    }
    @PostMapping("/login")
    public Result login(@RequestBody User user) {
        return loginService.loginInto(user);
    }
    @PostMapping("/logOut")
    public Result logOut(HttpServletRequest request){
        return loginService.logOut(request.getHeader("token"));
    }
}
