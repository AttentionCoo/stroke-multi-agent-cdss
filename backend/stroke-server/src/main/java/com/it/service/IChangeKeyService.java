package com.it.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.it.pojo.ChangeKey;
import com.it.pojo.Result;
import com.it.po.uo.User;

public interface IChangeKeyService extends IService<User>{

    Result changeKeyById(Long currentId, ChangeKey changeKey);



    Result getUserInfo(Long currentId);
}
