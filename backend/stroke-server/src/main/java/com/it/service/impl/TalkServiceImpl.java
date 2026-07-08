package com.it.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.mapper.TalkMapper;
import com.it.pojo.Talk;
import com.it.service.ITalkService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class TalkServiceImpl extends ServiceImpl<TalkMapper, Talk> implements ITalkService {
}
