---
tid: "t107"
slug: "write_path_lifecycle_domain_boundaries"
title: "Profile 写路径与运行时生命周期领域边界重构"
status: "done"
branch: "t107_write_path_lifecycle_domain_boundaries"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "3180cb90d72829eadadd481e73517f83c2188990"
spec_source_sha: "3180cb90d72829eadadd481e73517f83c2188990"
depends_on: ""
conflicts_with: ""
note: "来源 p167；实测 5 函数 CC>=15，manifest.extract_directory_metadata 已降至14故剔除；按领域建模重构而非机械拆分"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 写路径：`ProfileService.update_profile` 拆出 `_patch_dict`、`_resolve_platform_binding`、`_validate_patch_references`、`_validate_patch_extensions`；`ProfileRepository.update_profile` 拆出配置读/写投影、版本跃迁、快照、审计与幂等重放，字段来自 `ProfileConfig.model_fields`，删除手工字段清单。
- 扩展迁移：`_match_legacy_entry` 的判定抽为纯 `_classify_managed_candidates` 与身份/核心哈希匹配 helper，结论文案留在入口。
- 生命周期：`start_profile` 拆为会话前置、意图断言、实例绑定、装配、容器启动、会话提交、失败收尾七个阶段；`restore_point` 拆为路径、schema 守卫、陈旧清扫、暂存、单项切换五个阶段。`test_t075_supervisor_fonts.py` 的 mock 改用 `monkeypatch.setattr`。
- 门禁 `scripts/run_gates.sh` exit 0；黑盒 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` exit 0（108 例，镜像按当前提交重建，隔离端口 31000/10.252 网段）。
- CC 复测（AST 近似 McCabe）：`update_profile` 12/11、`start_profile` 7、`restore_point` 4、`_match_legacy_entry` 11，分类 helper 12；全部低于 15。
- 陷阱：全新 worktree 缺前端 node_modules、Selkies wheel 缓存与 jpeginfo，按已忽略路径软链主仓缓存；黑盒默认端口与宿主正式栈冲突，故用隔离泳道。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-24T06:20:12+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t107_code_f001|important|已修|审计写入改用 `_record_operation_audit(..., now=now)`，恢复显式 created_at 并消除 helper 分叉|src/backend/cbrowser/adapters/database/repository.py:776|
|t107_code_f002|minor|已修|移除 `_switch_item` 的死参数 `point` 及两处调用实参|scripts/restore_point.py:746|
|t107_code_f003|minor|已修|`_match_legacy_entry` 不再计算未使用的 key_sha|src/backend/cbrowser/adapters/database/extension_paths_migration.py:352|
|t107_test_f001|important|已修|新增 3 例直测：引用校验、扩展校验、平台/字体绑定的独立调用与异常断言|tests/unit/test_t107_domain_boundaries.py|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`scripts/run_gates.sh` exit 0；后端 unit/integration 全绿，前端测试与生产构建通过；新增 `tests/unit/test_t107_domain_boundaries.py` 12 例直测新边界（字段投影覆盖、身份分类、启动前置与失败原因、恢复路径/schema/单项切换）。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` exit 0，108 例通过（2 skipped），镜像由当前提交重建并锁定 sha256。
- review：full 双轴，Round 1 code/test 共 4 条 finding（1 important 审计时间漂移、1 important AC-005 缺直测、2 minor 死参数/死变量）全部修复；Round 2 双轴 PASS，`task.py review-status` overall=PASS / review_scope=ok / ac_review=ok，2 轮，未超 5 轮上限。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 写路径与生命周期改为领域边界编排，新增配置字段不再存在第二份手工清单；对外行为、API、DB schema 与恢复点格式不变。
- 遗留：无。
- specs_index：`docs/specs/profile_management.md`、`docs/specs/runtime_lifecycle.md`、`docs/specs/storage_and_artifacts.md` 的 `tasks` 均已登记 t107；`docs/blueprint/architecture.md` 与 `docs/blueprint/decisions/20261124_write_path_domain_boundaries.md` 已同步。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
