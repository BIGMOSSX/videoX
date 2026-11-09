# 多市场 UGC 语言扩展 Implementation Plan

> **For agentic workers:** 使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 逐任务执行；复用用户要求的资深工程、UI 和 Sol 独立验收分工。下方复选框用于进度追踪。

**Goal:** 在现有 UGC 客户端增加四市场口播语言和手动台词语言不一致提醒。

**Architecture:** 市场随任务持久化，以可信配置驱动导演、场景检索和视频提示词；旧任务按巴西兼容。语言检查为独立、可失败的非阻塞提示，保留用户台词原文。

**Tech Stack:** Python、FastAPI、Pydantic、SQLite JSON、React、TypeScript、现有测试工具。

**Spec:** `docs/multimarket-ugc-spec.md`；实施前先完整阅读。

## Global Constraints

- 市场值为 `pt-BR`、`es-MX`、`en-US`、`fil-PH`，默认 `pt-BR`。
- 保留既有创作体验、参考图与 15 秒一镜到底约束；UI 使用现有组件。
- 保留旧数据及原有非跟踪素材；不将人物图片、凭据提交或上传到仓库。
- 不自行运行付费视频生成；真实样片按项目付费确认流程进行。

## Review Focus

- 旧 `draft_ready` 任务在提交时会重新编译提示词，必须保留巴西语言。
- 非巴西导演 system prompt 不可与目标语言发生冲突。
- Filipino 借用英语、短句及专有名词不能被高置信误判。
- 语言检查失败和内容变化必须清晰处理，不能让旧检查结果继续生效。
- 切换表单市场不能改变进行中和历史任务的市场或造成重复付费。

## Task 1：任务级市场与兼容契约

**Files:** `studio/models.py`、新建 `studio/languages.py`、`schemas/artifacts/ugc_draft.schema.json`、`studio/service.py`、`studio-web/src/api.ts`、`tests/studio/test_contract.py`、`tests/studio/test_api.py`。

**Interfaces:** `Brief` / `BatchBrief` 增加 `language`，批量展开传递；统一目录提供四种受限值和展示名称。新草稿使用通用 `dialogue`，读取旧 `dialogue_pt_br` 时按规格兼容；packet 包含语言与版本信息。

- [ ] 先写测试：默认及非法值、四语言批量展开、旧字段读取、冲突字段拒绝、旧 checkpoint 与旧待提交任务兼容。
- [ ] 运行相关测试确认新增断言先失败；实现模型、schema、packet 和旧数据适配，保留原始历史数据。
- [ ] 重跑测试，验证进行中的任务不重新提交，且历史语言不依赖当前表单。

## Task 2：导演、场景与网关提示词

**Files:** `studio/director.py`、`studio/pinterest.py`、`studio/models.py`、`studio/service.py`、`studio/providers.py`、`skills/pipelines/brazil-ugc-game-ad/`、`pipeline_defs/brazil-ugc-game-ad.yaml`、`tests/studio/test_providers.py`、`test_contract.py`、`test_pinterest.py`。

**Interfaces:** `compile_prompt(brief, draft)` 使用任务语言；场景查询请求携带市场；三个 provider 收到同一目标语言提示词。

- [ ] 先写四语言参数化测试，检查导演 system 指令、场景检索、最终 prompt、手动原文及全部参考图约束；非巴西用例断言不含强制 pt-BR。
- [ ] 实现可信的市场化导演规则、场景搜索和 prompt；保留 pipeline 稳定 ID，更新用户可见说明及视频审查语言。
- [ ] 核实并修正 Flova 分辨率指令冲突；mock 验证 Ark、WaveSpeed、Flova 的任务语言传递与原有防重复付费逻辑。
- [ ] 运行对应测试直至通过。

## Task 3：台词不一致提示

**Files:** 新建 `studio/language_check.py`；修改 `studio/app.py`、`studio/models.py`、`studio-web/src/App.tsx`、`studio-web/src/api.ts`、`tests/studio/` 与前端工作流测试。

**Interfaces:** `POST /api/language-check` 接收 `{language, dialogue_lines}`；逐行返回 `match`、`likely_mismatch` 或 `uncertain` 与可读提示。使用已配置导演模型，不发送参考图片；失败返回可识别的检查失败状态。

- [ ] 先写测试：完整异语言、正确语言、短句、品牌名、Taglish、空白、CRLF、10 行仅第 7 行不一致、检查失败；确认返回与行映射，原文未改写。
- [ ] 实现结构化检查与保守结果解析；只对高置信差异提醒，模型不可用时提供明确状态。调用费用提示清楚。
- [ ] 输入失焦或防抖触发检查；市场或台词改变时使旧结果失效。提醒含行号、目标语言、可继续操作；失败不阻塞创建。
- [ ] 测试失效、继续、行数校验、无图片上传以及不触发视频生成。

## Task 4：客户端市场选择与历史显示

**Files:** `studio-web/src/App.tsx`、`studio-web/src/components/DraftReview.tsx`、`studio-web/src/components/SettingsPanel.tsx`、`studio-web/src/api.ts`、必要的现有样式与 `studio-web/src/workflow.test.tsx`。

- [ ] 先写交互测试：默认巴西、四选项、批量请求、动态台词标签、切换保留原文、旧任务回退巴西、历史任务不随新表单变化。
- [ ] 用现有 `Field` 和原生可访问选择器实现市场选择；现有任务卡、草稿、`lang` 属性与帮助文案使用任务语言。
- [ ] 提醒关联输入框并支持键盘和屏幕阅读器；检查窄屏布局。
- [ ] 运行前端测试、类型检查与构建。

## Task 5：独立验收与交付

**Files:** `README_STUDIO.md`、`docs/multimarket-ugc-spec.md`、相关打包及测试文件。

- [ ] 执行 `.venv/bin/python -m pytest tests/studio -q`；在 `studio-web` 执行 `pnpm test`、`pnpm typecheck`、`pnpm build`；运行现有打包测试。按实际环境记录结果。
- [ ] 由 Sol 模型独立检查差异、旧任务、供应商路径、语言检测误判、UI 和测试遗漏；修复可复现问题并复测。
- [ ] 如开展真实生成，先说明供应商、模型、样片数量和预计费用；逐市场人工核对发音、口音、口型、屏幕和一镜到底。未实测明确列出。
- [ ] 更新 README 中市场、语言检查成本、历史兼容与真实测试范围。重新打包前确认不包含密钥；只按已有授权处理本地素材。

## 新窗口交接

在 `/home/robin/项目/视频生成自动化改造/videoX` 工作。先读 `AGENTS.md`、`AGENT_GUIDE.md`、规格和本计划；检查 Git 状态并保留现有未跟踪素材。按照上面步骤实施、测试和独立验收，不要把本文档当成已经完成的实现。不要将 API 密钥写入代码、日志或提交。
