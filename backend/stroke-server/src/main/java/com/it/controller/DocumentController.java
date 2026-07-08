package com.it.controller;

import com.it.pojo.DocumentUrlVO;
import com.it.pojo.DocumentVO;
import com.it.pojo.Result;
import com.it.service.OssDocumentService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * OSS 文档访问接口
 * 所有接口均需 JWT 认证（由全局 TokenInterceptor 拦截）
 */
@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/documents")
@RequiredArgsConstructor
public class DocumentController {

    private final OssDocumentService ossDocumentService;

    /**
     * GET /api/documents
     * 返回按分类分组的文档列表
     * 响应示例：{ "code": 0, "data": { "指南": [{id, name, category, size}], "教材": [...] } }
     */
    @GetMapping
    public Result listDocuments() {
        try {
            Map<String, List<DocumentVO>> docs = ossDocumentService.listDocuments();
            return Result.success(docs);
        } catch (Exception e) {
            log.error("[文档列表] 获取失败", e);
            return Result.error("获取文档列表失败：" + e.getMessage());
        }
    }

    /**
     * GET /api/documents/{id}/url
     * 根据文档 ID 生成预览和下载签名 URL（有效期 30 分钟）
     * 响应示例：{ "code": 0, "data": { "id": "...", "previewUrl": "https://...", "downloadUrl": "https://..." } }
     */
    @GetMapping("/{id}/url")
    public Result getSignedUrl(@PathVariable String id) {
        try {
            DocumentUrlVO urlVO = ossDocumentService.generateSignedUrl(id);
            return Result.success(urlVO);
        } catch (Exception e) {
            log.error("[签名URL] 生成失败，id={}", id, e);
            return Result.error("生成签名 URL 失败：" + e.getMessage());
        }
    }

    /**
     * GET /api/documents/match?name=急性缺血性脑卒中诊治指南
     * 按文献名模糊匹配文档，匹配成功时返回签名 URL，未找到返回 404
     */
    @GetMapping("/match")
    public Result matchDocument(@RequestParam String name) {
        try {
            DocumentUrlVO urlVO = ossDocumentService.matchByName(name);
            if (urlVO == null) {
                return Result.error("未找到与「" + name + "」匹配的文档");
            }
            return Result.success(urlVO);
        } catch (Exception e) {
            log.error("[文献匹配] 匹配失败，name={}", name, e);
            return Result.error("文献匹配失败：" + e.getMessage());
        }
    }
}
