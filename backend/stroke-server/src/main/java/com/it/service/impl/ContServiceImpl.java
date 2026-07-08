package com.it.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.mapper.ContMapper;
import com.it.mapper.TalkMapper;
import com.it.po.uo.Cont;
import com.it.pojo.Talk;
import com.it.service.IContService;
import com.it.service.ITalkService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class ContServiceImpl extends ServiceImpl<ContMapper, Cont> implements IContService {
}
