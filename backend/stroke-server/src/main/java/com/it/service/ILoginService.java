package com.it.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.it.pojo.Result;
import com.it.po.uo.User;

public interface ILoginService extends IService<User> {
    Result loginInto(User user);

    Result logOut(String token);
}
