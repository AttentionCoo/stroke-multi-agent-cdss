package com.it.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.it.pojo.Result;
import com.it.po.uo.User;

public interface IRegiService extends IService<User> {
    Result insertUser(User user);
}
