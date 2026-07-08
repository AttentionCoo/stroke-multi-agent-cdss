package com.it.mapper;

import com.it.pojo.Talk;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface QuesMapper {
    public String findExContent(Long userId, Long talkId);

    boolean notNULL(Long userId, Long talkId);

    void insertTalk(Talk talk);

    void updateTalk(Talk currentTalk);

    List<String> findAllExContent(Long userId, Long talkId);

    void insertContent(Long userId, Long talkId, String content, String createTime);
}
