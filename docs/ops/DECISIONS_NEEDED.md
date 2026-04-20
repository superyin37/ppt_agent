---
name: 待决策问题
description: 等人类拍板才能推进的开放问题 — 对 Coding Agent 最关键的文档
last_updated: 2026-04-20
owner: superxiaoyin
---

# 待决策问题(Decisions Needed)

> 对 Coding Agent 最关键的一份文档。**所有"需要你拍板才能继续"的问题都列在这里**,避免 Agent 自作主张或卡住。
> **更新规则**:决策后该条目移入 [decisions/](decisions/) 并在此删除。

---

## 🔴 阻塞开发

*(当前无 — 所有 P0 问题都已决策并在执行)*

## 🟡 影响规划

### DN-001:Nanobanana vs 其他图像生成服务
- **问题**:蓝图"概念方案"9 页依赖 AI 图像生成,Nanobanana 是最初设想但尚未验证
- **需要决策**:
  - (A) 坚持 Nanobanana,补集成
  - (B) 换 SDXL / DALL-E 3 / Flux 其一
  - (C) 先占位,等人工上传效果图
- **影响**:P1-2 任务的实施方式
- **建议**:(C) 先不阻塞核心链路,验证完内容质量后再决定图像方案

### DN-002:联网搜索服务选型
- **问题**:蓝图"背景研究/竞品分析"14 页依赖 web_search
- **需要决策**:
  - (A) Tavily / Perplexity / Exa 选一
  - (B) 自建基于 SerpAPI 的简单检索
  - (C) 用 Claude 原生 web search 工具
- **影响**:P1-3 任务
- **建议**:(C) 如果用 Claude API 直接内置最便捷

### DN-003:PPTX 导出是否进入一期验收
- **问题**:`python-pptx` 依赖已装但未实现
- **需要决策**:
  - (A) 一期 PDF-only,PPTX 进 M4
  - (B) 一期就上 PPTX
- **影响**:M3 vs M4 范围
- **建议**:(A) PDF 已验证,PPTX 不影响核心演示

## 🟢 可延后

### DN-004:前端技术栈
- **问题**:当前 [frontend/](../../frontend/) 是原生 HTML/JS,M4 考虑升级
- **需要决策**:React / Vue / Svelte / 保持原生
- **影响**:M4 规划
- **建议**:不急,M3 完成后再定

### DN-005:案例库填充责任方
- **问题**:`scripts/seed_cases.json` 仍是占位
- **需要决策**:谁负责收集真实建筑案例(用户?外包?爬虫?)
- **影响**:Reference Agent 的实际推荐质量

---

## 格式约定

每条决策问题包含:
- **编号** `DN-XXX`(永不回收)
- **问题** — 一句话描述
- **选项** (A)(B)(C)…
- **影响** — 不决策会卡住什么
- **建议** — 我/AI 的倾向,供参考

决策后:
1. 在本文件删除该条
2. 在 [decisions/](decisions/) 新建 `ADR-NNN-<slug>.md` 记录决策与理由
3. 在 [BUGS.md](BUGS.md) 或 [TODO.md](TODO.md) 中引用该 ADR
