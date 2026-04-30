# Agent 评估平台 - 完整开发计划

## 项目概述

**目标**: 搭建一个 Agent 应用评估平台，支持多种评测方法、多维度指标和对比分析。

**当前状态**: Phase 1 完成 (约 85%)，核心功能可用，待完成过程评测数据接入和异步任务队列。

---

## Phase 2: 核心功能完善 (优先级：高)

### 2.1 过程评测真实数据接入

**目标**: 将 `ProcessEvaluationService` 与真实 Agent Trace 数据对接

**当前问题**:
- `process_evaluation_service.py` 已实现但未在评测流程中被调用
- `_get_process_metrics_stub()` 返回模拟数据

**任务分解**:

| 序号 | 任务 | 预计工时 | 涉及文件 |
|------|------|----------|----------|
| 2.1.1 | 定义 Trace 数据存储格式和采集接口 | 2h | `models/trace.py`, 新增 `api/routes/traces.py` |
| 2.1.2 | 实现 Trace 数据上传 API | 1h | `api/routes/traces.py` |
| 2.1.3 | 修改 `evaluation_service.py` 调用真实 process 评测 | 2h | `services/evaluation_service.py` |
| 2.1.4 | 添加 Trace 数据加载器 (从文件/数据库) | 1h | 新增 `services/trace_loader.py` |
| 2.1.5 | 前端添加 Trace 可视化展示 | 3h | 新增 `components/TraceViewer.tsx` |

**交付物**:
- [ ] Trace 数据上传接口 `/api/traces/`
- [ ] 评测任务执行时自动加载/计算过程指标
- [ ] 前端 Trace 查看器

---

### 2.2 异步任务队列集成

**目标**: 支持大数据集评测不阻塞 API，实现实时进度查询

**任务分解**:

| 序号 | 任务 | 预计工时 | 涉及文件 |
|------|------|----------|----------|
| 2.2.1 | 添加 Redis Docker 配置 | 0.5h | `deploy/docker-compose.yml` |
| 2.2.2 | 安装 Celery 和 Redis 依赖 | 0.5h | `backend/pyproject.toml` |
| 2.2.3 | 创建 Celery App 配置 | 1h | 新增 `backend/app/workers/celery_app.py` |
| 2.2.4 | 实现评测任务 Worker | 2h | 新增 `backend/app/workers/evaluation_worker.py` |
| 2.2.5 | 修改 `run_task` API 为异步启动 | 1h | `api/routes/tasks.py` |
| 2.2.6 | 添加任务进度查询 API | 1h | `api/routes/tasks.py` |
| 2.2.7 | 前端实现进度轮询组件 | 2h | 新增 `components/TaskProgress.tsx` |
| 2.2.8 | 添加任务超时和重试配置 | 1h | `backend/app/core/config.py`, worker |

**交付物**:
- [ ] Celery Worker 服务
- [ ] 异步评测 API (`POST /tasks/{id}/run` 返回任务 ID)
- [ ] 进度查询 API (`GET /tasks/{id}/progress`)
- [ ] 前端进度条组件

---

### 2.3 数据集管理功能

**目标**: 支持通过前端上传/管理评测数据集

**任务分解**:

| 序号 | 任务 | 预计工时 | 涉及文件 |
|------|------|----------|----------|
| 2.3.1 | 实现数据集上传 API | 1.5h | `api/routes/datasets.py` |
| 2.3.2 | 实现数据集列表 API | 0.5h | `api/routes/datasets.py` |
| 2.3.3 | 实现数据集删除 API | 0.5h | `api/routes/datasets.py` |
| 2.3.4 | 前端添加数据集管理页面 | 2h | 新增 `pages/DatasetsPage.tsx` |
| 2.3.5 | 前端添加数据集上传组件 | 1.5h | 新增 `components/DatasetUploader.tsx` |
| 2.3.6 | 更新 metadata API 返回可用数据集 | 0.5h | `api/routes/metadata.py` |

**交付物**:
- [ ] 数据集 CRUD API
- [ ] 前端数据集管理页面
- [ ] 支持 JSONL 格式验证

---

## Phase 3: 增强功能 (优先级：中)

### 3.1 可视化图表集成

**目标**: 添加评测结果图表展示（当前 `charts` 字段未渲染）

**任务分解**:

| 序号 | 任务 | 预计工时 | 涉及文件 |
|------|------|----------|----------|
| 3.1.1 | 安装图表库 (Recharts) | 0.5h | `frontend/package.json` |
| 3.1.2 | 实现维度雷达图组件 | 2h | 新增 `components/DimensionRadarChart.tsx` |
| 3.1.3 | 实现指标柱状图组件 | 1.5h | 新增 `components/MetricBarChart.tsx` |
| 3.1.4 | 实现时间线进度组件 | 1h | 新增 `components/TimelineProgress.tsx` |
| 3.1.5 | 在 TaskDetailPage 中集成图表 | 1h | `pages/TaskDetailPage.tsx` |
| 3.1.6 | 对比页面添加对比图表 | 2h | `components/ComparisonPanel.tsx` |

**交付物**:
- [ ] 雷达图：展示 quality/safety/performance 三维度对比
- [ ] 柱状图：各细分指标分数对比
- [ ] 时间线：评测流程可视化

---

### 3.2 LLM-as-a-Judge 自定义提示词

**目标**: 允许用户自定义 Judge 评估的提示词

**任务分解**:

| 序号 | 任务 | 预计工时 | 涉及文件 |
|------|------|----------|----------|
| 3.2.1 | 扩展 Schema 支持自定义提示词 | 0.5h | `schemas/task.py` |
| 3.2.2 | 修改 RagasService 支持自定义 prompt | 1.5h | `services/ragas_service.py` |
| 3.2.3 | 添加预设提示词模板库 | 1h | 新增 `services/judge_prompts.py` |
| 3.2.4 | 前端添加提示词编辑器 | 2h | 新增 `components/PromptEditor.tsx` |

**交付物**:
- [ ] 自定义 Judge 提示词配置
- [ ] 预设模板库（推理质量、幻觉检测、安全性等）

---

### 3.3 评测报告导出

**目标**: 支持导出评测报告为 PDF/Markdown/JSON 格式

**任务分解**:

| 序号 | 任务 | 预计工时 | 涉及文件 |
|------|------|----------|----------|
| 3.3.1 | 实现 JSON 导出 API | 0.5h | `api/routes/reports.py` |
| 3.3.2 | 实现 Markdown 报告生成 | 1.5h | `services/report_service.py` |
| 3.3.3 | 实现 PDF 导出 (使用 WeasyPrint 或类似) | 2h | `services/report_service.py` |
| 3.3.4 | 前端添加导出按钮 | 1h | `pages/TaskDetailPage.tsx` |

**交付物**:
- [ ] `GET /api/reports/{task_id}?format=json|md|pdf`
- [ ] 包含分数卡、指标详情、图表的报告

---


## 开发优先级总览

```
Phase 2 (核心完善)
├── 2.1 过程评测数据接入  ████████░░ 80% (模型已定义，待接入)
├── 2.2 异步任务队列      ░░░░░░░░░░ 0%
└── 2.3 数据集管理        ░░░░░░░░░░ 0%

Phase 3 (增强功能)
├── 3.1 可视化图表        ░░░░░░░░░░ 0%
├── 3.2 自定义 Judge 提示词 ░░░░░░░░░░ 0%
└── 3.3 评测报告导出      ░░░░░░░░░░ 0%


---

## 预计总工时

| Phase | 预估工时 | 说明 |
|-------|----------|------|
| Phase 2 | ~18 小时 | 核心功能完善 |
| Phase 3 | ~12 小时 | 增强功能 |
| **总计** | **~52 小时** | 约 6-7 个工作日 |

---

## 下一步立即行动项

1. **2.1 过程评测数据接入** - 这是当前唯一标记为"部分完成"的核心功能
2. **2.2 异步任务队列** - 解决同步执行阻塞问题
3. **3.1 可视化图表** - 提升用户体验

---

## 技术栈补充

### 后端需添加
- `celery>=5.3`
- `redis>=4.5`
- `weasyprint` (PDF 导出)

### 前端需添加
- `recharts` (图表库)
- `@tanstack/react-query` (可选，优化 API 请求)

---

## 风险与注意事项

1. **Ragas 版本兼容性** - 确保 `langchain` 和 `ragas` 版本兼容
2. **大数据集性能** - 超过 100 条样本的评测必须使用异步队列
3. **LLM API 成本** - Judge 评估会消耗较多 Token，建议添加成本估算功能
4. **数据隐私** - 生产环境需加密存储评测数据
