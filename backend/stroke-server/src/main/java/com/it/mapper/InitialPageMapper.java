package com.it.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.it.po.vo.InitialPageVO;
import com.it.pojo.Talk;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface InitialPageMapper extends BaseMapper<Talk> {
//    //@Select("select id as talkId, title from talk where user_id=#{currentId} order by create_time desc")
//    List<InitialPageVO> getPage(Integer currentId);
//
//
//    void deleteTalk(Integer userId, Integer talkId);
}
