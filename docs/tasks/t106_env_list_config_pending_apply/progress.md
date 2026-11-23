---
tid: "t106"
slug: "env_list_config_pending_apply"
title: "配置变更待应用状态统一并在环境管理列表暴露"
status: "done"
branch: "t106_env_list_config_pending_apply"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "9940cd79c2020bdeff43a5a453df9203356a7b85"
spec_source_sha: "9940cd79c2020bdeff43a5a453df9203356a7b85"
depends_on: ""
conflicts_with: ""
note: "来源 p170；用户裁决行内提供应用并重启; 架构复核升级：config_pending 作为领域派生事实进入读模型，前端删除版本比较式"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 后端：`domain/models.py` 定义唯一 `config_pending` 谓词并加入三个读模型；`profile_service.list_profiles_page`、`make_runtime_response` 与共享 `make_runtime_event_data` 统一填充（SSE 初始快照与实时发布共用该工厂）；契约经 `scripts/export_openapi.py` 与 `npm run generate:api` 破坏性重导。
- 前端：删除视图层版本比较，新增 `ConfigPendingNotice` 单一呈现单元与 `useApplyConfigRestart` 单一命令；列表表格/卡片、工作台入口、会话页头/详情统一消费 `runtime.config_pending`；同步修正全部既有 fixture 的必填字段。
- 验证：门禁 `scripts/run_gates.sh` 全绿（模板契约、后端单元/集成、前端测试、类型、设计 lint/check、生产构建）；黑盒 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 全绿（108 例，使用当前代码重构建的六镜像与隔离端口泳道，先以独立镜像与默认端口复现环境冲突后改用 31000/10.252 网段）。
- 陷阱：全新 worktree 缺前端 node_modules、Selkies wheel 缓存与 jpeginfo，按已忽略路径软链主仓缓存；并行 E2E 与宿主正式栈争用 30000 端口，非产品缺陷。
- 来源 p170 在立项阶段已按 bug-to-pending 流程 closed/transferred 到 t106，`pending.py` 不允许对 closed 条目重复闭环，故不在本 task 再写 resolved。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-24T00:50:11+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t106_test_f001|important|已修|SSE 填充改为共享 `make_runtime_event_data` 生产工厂，真值表由其驱动，快照与实时发布均经该工厂|src/backend/cbrowser/api/v1/runtime_views.py:105|

### Round 2 (2026-11-24T01:10:00+08:00)

Round 2 零 finding；code/test 双轴 PASS，`task.py review-status` overall=PASS、review_scope=ok、ac_review=ok。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`scripts/run_gates.sh` exit 0；后端 2777 unit + integration 用例全绿，前端 756 用例全绿，类型/设计门禁与生产构建通过；新增 `tests/unit/test_t106_config_pending.py` 覆盖谓词真值表、三个读模型与配置抬升后的集合行翻转。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` exit 0，108 例 E2E 通过（2 skipped），镜像由当前提交重建并锁定 sha256，端口与媒体网段隔离。
- review：full 双轴，Round 1 测试轴 1 条 important（SSE 填充恒真断言）已修；Round 2 code/test 双轴 PASS，`task.py review-status` overall=PASS / review_scope=ok / ac_review=ok，2 轮，未超 5 轮上限。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 待应用状态由领域派生事实进入读模型，环境管理表格/卡片与工作台入口不再静默显示「运行中」；行内「应用并重启」让用户在列表原地完成重启，无需跳转工作台。
- 遗留：无。
- specs_index：`docs/specs/profile_management.md` 的 `tasks` 已登记 t106，并新增待应用读模型口径；`docs/blueprint/{domain,architecture,frontend}.md` 与 `docs/blueprint/decisions/20261123_config_pending_read_model.md` 已同步。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
