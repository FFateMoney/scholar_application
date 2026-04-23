# AutoScholar 项目介绍

## 项目概述

AutoScholar 是一个面向学术研究场景的智能工作流系统，用于把“想法整理、文献检索、证据筛选、可行性评估、报告生成”串成一条结构化流水线。

它的目标不是只生成一段答案，而是构建一个可追踪、可复用、可验证的研究支持流程，让用户能够基于清晰的中间产物完成学术调研与方案分析。

## 项目要解决的问题

传统的学术调研和选题分析通常存在几个痛点：

- 从研究想法到检索关键词，过程依赖人工整理，效率低
- 检索结果数量大，但缺少结构化筛选和证据归纳
- 生成报告时，中间推理过程不透明，难以核查来源
- 文献、结论、报告常常分散在不同工具中，不便复用

AutoScholar 的核心价值，就是把这些分散步骤整合成一个统一系统，并通过结构化产物保存全过程。

## 核心能力

- 研究想法输入与拆解：把自然语言想法转成 claims、queries 等结构化信息
- 文献检索与重试：基于 Semantic Scholar 执行检索，并对失败查询进行重试管理
- 文献预筛与纠偏：对检索结果做 prescreen、correction、shortlist，提升证据质量
- 证据映射与方案评估：围绕研究想法生成 evidence map，并输出 feasibility assessment
- 报告生成：自动生成可读的 Markdown 报告
- BibTeX 支持：支持参考文献提取与 BibTeX 生成
- 前后端联动：提供本地 FastAPI 服务和前端界面，支持任务提交、进度查询和结果预览

## 系统架构

整个项目由三部分组成：

### 1. AutoScholar 核心引擎

位于 `AutoScholar/`，是项目的核心 Python 包，提供统一 CLI 和研究工作流能力。

主要模块包括：

- `citation/`：负责文献检索、预筛、纠偏、短名单生成、BibTeX 输出
- `analysis/`：负责研究想法评估
- `reporting/`：负责 evidence map 构建、报告渲染与校验
- `integrations/semantic_scholar.py`：负责对接 Semantic Scholar
- `workspace.py`：负责工作空间初始化与路径管理
- `cli.py`：提供统一的 `autoscholar` 命令行入口

### 2. Backend 服务

位于 `backend/`，基于 FastAPI，负责把 AutoScholar 封装成可调用的本地服务。

目前主要提供两类任务：

- `idea report`：输入研究想法，输出完整分析报告
- `reference bib lookup`：输入文档或文本，提取参考文献并生成 BibTeX

后端会为每个任务创建独立运行目录，保存输入、日志、结构化中间产物和最终结果，便于追踪和调试。

### 3. Frontend 界面

位于 `frontend/`，是一个轻量级静态前端，用于：

- 提交任务
- 查看任务状态
- 预览最终结果
- 在开发模式下查看调试日志

这让项目不仅能作为命令行工具使用，也能作为一个本地可交互应用运行。

## 工作流说明

以 `idea report` 为例，项目的大致流程如下：

1. 用户输入一个研究想法
2. 系统调用 Codex 生成想法摘要、关键 claims 和检索 queries
3. AutoScholar 调用 Semantic Scholar 执行文献检索
4. 系统对检索结果进行预筛、纠偏和候选证据收敛
5. 基于筛选后的文献构建 evidence map
6. 执行 idea assessment，形成对方案可行性和创新性的判断
7. 渲染内部结构化报告
8. 再由 Codex 生成面向用户的最终 Markdown 报告
9. 可选地对最终报告进行复审和修订

这一流程的特点是：既有模型生成能力，也有结构化数据和规则化处理，避免完全依赖一次性文本输出。

## 数据与产物设计

项目非常强调“结构化中间结果”，常见产物包括：

- `claims.jsonl`
- `queries.jsonl`
- `search_results.raw.jsonl`
- `search_results.deduped.jsonl`
- `query_reviews.json`
- `recommendation_corrections.jsonl`
- `selected_citations.jsonl`
- `idea_assessment.json`
- `evidence_map.json`
- `references.bib`

这些文件不是附属信息，而是整个系统可信性和可复用性的关键。相比只输出一篇最终报告，这种设计更方便：

- 回溯结论来源
- 检查检索质量
- 替换单个步骤重新运行
- 支持后续分析和二次开发

## 项目特点

- 工作流完整：覆盖从研究想法到最终报告的完整链路
- 结构化优先：中间结果以 JSON/JSONL/Markdown 等形式沉淀
- 可验证：报告不是黑盒生成，而是基于 claims、citations、evidence map 构建
- 易扩展：核心能力通过 Python 包和 CLI 暴露，便于集成
- 可服务化：通过 FastAPI 封装后，可以直接被前端或其他系统调用
- 面向 Agent：项目天然适合与 LLM Agent 协同，支持自动化研究辅助

## 适用场景

- 研究选题评估
- 学术文献调研
- 论文前期论证
- 方案可行性分析
- 参考文献整理与 BibTeX 生成
- 面向智能体的学术辅助系统原型

## 一句话总结

AutoScholar 是一个将大模型能力、学术检索、证据筛选和报告生成结合起来的智能研究工作流平台，重点不只是“生成内容”，而是“生成有来源、有结构、可追踪的研究结论”。
