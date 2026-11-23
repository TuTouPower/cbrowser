# Task review t107（reviewer_focus: 代码）

- task：`t107_write_path_lifecycle_domain_boundaries`
- spec：`docs/tasks/t107_write_path_lifecycle_domain_boundaries/task.md`
- diff_anchor：`3180cb90d72829eadadd481e73517f83c2188990`
- target：`git diff 3180cb90d72829eadadd481e73517f83c2188990`
- round：1
- reviewed_at：2026-11-24T06:14:39+08:00

reviewed_scope: 6f5e2449f967f357

## Findings

### t107_code_f001 - 审计写入 helper 丢失 created_at，重放审计时间发生语义漂移

- 严重度：important
- 锚点：行为缺陷 — 带 `operation_id` 调用 `update_profile` 时，审计行的 `created_at` 从旧实现的事务 `now` 变为 flush 时自动生成的更晚时间戳，与同事务内快照和 `updated_at` 不再一致。
- 位置：`src/backend/cbrowser/adapters/database/repository.py:773`（`_write_profile_audit`，构造体 `:782-791`），调用点 `:866`
- 问题：旧实现显式写 `created_at=now`（`git show 3180cb90...:src/backend/cbrowser/adapters/database/repository.py` 原 852-864 行），新 `_write_profile_audit` 构造 `AuditEventModel` 时未传 `created_at`，回落到模型默认 `default=utc_now_iso`（`src/backend/cbrowser/adapters/database/models.py:439-441`）。SQLAlchemy 列默认在 flush 时求值，而 `now` 在 `update_profile` 入口 `:827` 捕获，中间跨多次 await（版本 `max` 查询、代理凭证读取、快照写入）。结果：审计行 `created_at` 晚于 `ProfileConfigVersionModel.created_at=now` 与 `p_model.updated_at=now`；同文件已有标准 helper `_record_operation_audit`（`:177-203`）仍显式写 `created_at=now`，新 helper 与之分叉。全仓 grep 无任何 audit `created_at` 断言，该漂移无测试覆盖，属静默行为变化，与本 task「既有行为完全不变」的重构前提不符。
- 建议：给 `_write_profile_audit` 增加 `now: str` 参数并传 `created_at=now`；或复用 `_record_operation_audit(..., extra={"version": version})` 同时消除重复与漂移。

### t107_code_f002 - `_switch_item` 新增的 `point` 形参为死参数

- 严重度：minor
- 锚点：行为缺陷（可维护性）— 新 helper 签名暗示依赖 `point`，实际函数体从未引用它。
- 位置：`scripts/restore_point.py:746`（调用点 `:805`，测试 `tests/unit/test_t107_domain_boundaries.py:1921` 同样传入）
- 问题：`_switch_item(item, journal_path, journal, point, manifest)` 的 `point` 在 `:749-771` 函数体内无任何引用；`point_has_dir` 只用 `manifest` 与 `item["id"]`。死参数误导阶段边界的真实依赖。
- 建议：移除 `point` 形参及两处调用实参。

### t107_code_f003 - `_match_legacy_entry` 中 `key_sha` 计算后未使用

- 严重度：minor
- 锚点：行为缺陷（死代码）— 新入口重复计算 `key_sha`，实际只在 `_classify_managed_candidates` 内部被用到。
- 位置：`src/backend/cbrowser/adapters/database/extension_paths_migration.py:352-356`
- 问题：`cid, key_sha, ver = (...)` 中 `key_sha` 在 `:358-391` 未被引用（`cid`、`ver` 才用于文案与成功返回）；`_classify_managed_candidates`（`:318-321`）已自行从 `info` 重算同一值。重复计算并留下死变量。
- 建议：入口只解构 `cid`、`ver`（直接读 `info["chromium_id"]` / `info["version"]`），移除 `key_sha`。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：3 条（1 important、2 minor）。
- 未进表的提示：
    - 文件过大（按降级规则仅列路径与行数，不进 finding 表）：`src/backend/cbrowser/supervisor/core.py` 3675 行（旧 3623，净 +52）、`src/backend/cbrowser/adapters/database/repository.py` 3099 行（旧 3092，净 +7）、`src/backend/cbrowser/services/profile_service.py` 2366 行（旧 2357，净 +9）均超 800 行 important 阈值；`scripts/restore_point.py` 867 行（旧 821，净 +46）超 800；`src/backend/cbrowser/adapters/database/extension_paths_migration.py` 652 行超 400 minor 阈值。均为重构跨函数拆分导致的净增，diff 未给不可拆硬约束，按规则只在结论段提示。
    - 圈复杂度：AST 近似 McCabe 实测五目标函数与新分类 helper 为 11 / 11 / 8 / 4 / 11 / 14（`profile_service.update_profile` / `repository.update_profile` / `start_profile` / `restore_point` / `_match_legacy_entry` / `_classify_managed_candidates`），均 < 15，无复杂度 finding。
    - 范围外观察：无。改动面严格限于 5 个目标函数、新 helper 与一处 mock；未触碰对外 API、OpenAPI、DB schema、Alembic 迁移、恢复点格式与错误文案。
- 总体判断：跨 DB 事务、并发生命周期与恢复事务的重构经逐函数对比与测试复验，主体行为基本一致；但审计写入 helper 引入 `created_at` 静默漂移（f001），存在 1 条未解决 important → FAIL。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。逐条对比服务/仓储 `update_profile` 重构前后分支、调用顺序与事务边界一致；复跑 71 + 68 例（含 profile update、幂等、引用与扩展回归）全绿，API 响应与错误形状未变；审计时间漂移单列 f001。
- AC-002：TICK-VALID，re_verified。`start_profile` 阶段拆分后锁内顺序（前置→意图→陈旧清理→绑定→装配→容器→收敛→提交/失败收尾）与旧码一致，`_handle_start_failure` 的 reason 映射与事件/端口收尾等价；supervisor core / start_conflicts / startup_recovery 等 68 例全绿。
- AC-003：TICK-VALID，re_verified。`restore_point` 阶段 helper 与旧码逐行等价，`_switch_item` 保留 journal、`_fsync_dir` 与失败回滚语义；t066 恢复点与 t089 快照恢复测试全绿，恢复点格式与退出码未变。
- AC-004：TICK-VALID，re_verified。`_classify_managed_candidates` 的精确/核心哈希/歧义/缺失四类结论与文案逐项等价；t104 扩展迁移分类测试全绿。
- AC-005：TICK-VALID，re_verified。`_resolve_platform_binding`（`:753`）、`_validate_patch_references`（`:787`）、`_validate_patch_extensions`（`:793`）为可独立调用单元，`update_profile`（`:807`）编排仅调用、不再内联三类判断分支。
- AC-006：TICK-VALID，re_verified。`ProfileConfig.model_fields` 恰为旧 `current_dict` 的 22 字段且与 `ProfileModel` 列一一对应；`tests/unit/test_t107_domain_boundaries.py::test_config_orm_projection_covers_every_config_field` 对投影读写全字段断言通过。
- AC-007：TICK-VALID，re_verified。启动 7 阶段与恢复 5 阶段 helper 均可独立调用；`test_t107_domain_boundaries.py` 中 `test_start_session_precheck_is_independent`、`test_restore_paths_and_schema_guard_are_independent`、`test_switch_item_renames_live_and_writes_journal` 直接断言前置与回滚效果通过。
- AC-008：TICK-VALID，re_verified。`tests/unit/test_t075_supervisor_fonts.py:165` 改用 `monkeypatch.setattr`，`# type: ignore[method-assign]` 已移除，断言未变；该用例在 71 例复跑中通过。
- AC-009：TICK-VALID，re_verified。AST 近似 McCabe 实测五目标函数 + 分类 helper 为 11 / 11 / 8 / 4 / 11 / 14，均 < 15；数值已写入 `docs/tasks/t107_write_path_lifecycle_domain_boundaries/progress.md` 实施笔记。

coverage = 9 / 9

verdict: FAIL

## Round 2 (2026-11-24T07:02:47+08:00)

- round：2
- reviewed_at：2026-11-24T07:02:47+08:00

reviewed_scope: 29d45aeaded51059

## Findings

本轮无新 finding（finding_id 跨轮全局续编，下一个为 `t107_code_f004`）。

## 结论

- 前轮 finding 复核（以相对 `3180cb90d72829eadadd481e73517f83c2188990` 的当前完整交付为准，不采信 `progress.md` 处置表）：
    - `t107_code_f001`（important，审计 created_at 漂移）：已消除。当前 `src/backend/cbrowser/adapters/database/repository.py:847-856` 调用标准 helper `_record_operation_audit(..., sig_hash=sig_hash, now=now, extra={"version": new_version})`；helper 定义于 `:178-203`，`:201` 显式 `created_at=now`，`details` 由 `{"sig_hash": sig_hash}` 叠加 extra 合成（`:190-192`），与锚点版本 `git show 3180cb90...:src/backend/cbrowser/adapters/database/repository.py` 原 `:852-864` 的 `{"sig_hash": sig_hash, "version": new_version}` 及 `actor="system"`、entity 字段完全一致。全文件已无 `_write_profile_audit` 残留（grep 零命中），审计行不再回落到列默认值，漂移消除。
    - `t107_code_f002`（minor，`_switch_item` 死参数）：已消除。`scripts/restore_point.py:746-748` 签名收敛为 `_switch_item(item, journal_path, journal, manifest)`，函数体 `:749-771` 无 `point` 引用，`point_has_dir` 仅用 `manifest` 与 `item["id"]`；调用点 `:805` 与 `tests/unit/test_t107_domain_boundaries.py:234` 均传 4 实参。
    - `t107_code_f003`（minor，`key_sha` 死变量）：已消除。`src/backend/cbrowser/adapters/database/extension_paths_migration.py:352` 改为 `cid, ver = str(info["chromium_id"]), str(info["version"])`，入口不再计算未使用的 `key_sha`；分类 helper 内部自行读 `info["key_sha256"]`（`:316`）。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大（按降级规则仅列路径与行数，不进 finding 表）：`src/backend/cbrowser/supervisor/core.py` 3675 行、`src/backend/cbrowser/adapters/database/repository.py` 3081 行、`src/backend/cbrowser/services/profile_service.py` 2366 行、`scripts/restore_point.py` 867 行、`src/backend/cbrowser/adapters/database/extension_paths_migration.py` 648 行，均为本 task 拆分重构净增且 diff 未给不可拆硬约束，仅作提示；新测试 `tests/unit/test_t107_domain_boundaries.py` 373 行，未达测试 600 行阈值。
    - 圈复杂度：本轮 AST 近似 McCabe 实测 `profile_service.update_profile` 12、`repository.update_profile` 13、`supervisor.start_profile` 8、`restore_point` 4、`_match_legacy_entry` 11，新分类 helper `_classify_managed_candidates` 12，均 < 15；无复杂度 finding。
    - 范围外观察：无。本轮新增 3 例直接校验测试（引用校验、扩展校验、平台/字体绑定）属测试层，由 test reviewer 判定；本轴仅作为三类校验「可独立调用」的旁证。
- 总体判断：前轮唯一 blocker `t107_code_f001` 及两条 minor 均由当前 diff 独立证实消除，复跑 106 例相关回归全绿，未引入新 blocker，本轴无未解决 critical / important → PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。逐函数对比锚点 3180cb90 与当前：`repository.update_profile` 的版本跃迁/同值不抬升、快照、审计（`created_at=now` 已恢复）、幂等重放与异常映射分支一致，服务层三类校验调用顺序不变；复跑 `test_domain_and_repository`、`test_repository_idempotency`、`test_t056_references` 等 106 例全绿。
- AC-002：TICK-VALID，re_verified。`start_profile`（`src/backend/cbrowser/supervisor/core.py:2968`）拆分后锁内顺序（前置 `:3047`→意图 `:3069`→陈旧清理→绑定→装配→容器→收敛→提交/失败收尾 `:3297`）与锚点一致，`_handle_start_failure` 的 reason 映射与事件/端口收尾等价；`test_supervisor_start_conflicts`、`test_supervisor_startup_recovery`、`test_t075_supervisor_fonts` 全绿。
- AC-003：TICK-VALID，re_verified。`restore_point` 的 `_restore_paths`/`_assert_compatible_schema`/`_sweep_stale_staging`/`_stage_restore_items`/`_switch_item`（`scripts/restore_point.py:746`）与锚点逐段等价，journal、`_fsync_dir` 与失败回滚语义保留；`test_t066_restore_point` 全绿，恢复点格式与退出码未变。
- AC-004：TICK-VALID，re_verified。`_classify_managed_candidates`（`src/backend/cbrowser/adapters/database/extension_paths_migration.py:314`）四类结论与 `_match_legacy_entry`（`:342-387`）文案逐项等价，死变量 `key_sha` 已移除；`test_t104_extension_paths_migration` 全绿。
- AC-005：TICK-VALID，re_verified。`_resolve_platform_binding`（`src/backend/cbrowser/services/profile_service.py:753`）、`_validate_patch_references`（`:787`）、`_validate_patch_extensions`（`:793`）为可独立调用单元，`update_profile`（`:807`）编排仅调用、不再内联三类判断分支；3 例新增直测直接断言其独立行为。
- AC-006：TICK-VALID，re_verified。`_profile_config_from_model`（`src/backend/cbrowser/adapters/database/repository.py:699`）与 `_apply_config_to_model`（`:712`）以 `ProfileConfig.model_fields` 为唯一字段来源，旧 22 字段手工清单已删除；字段覆盖测试 `test_config_orm_projection_covers_every_config_field` 对读写全字段断言通过。
- AC-007：TICK-VALID，re_verified。启动阶段 helper（`_start_session_precheck` `:3047`、`_assert_start_intent` `:3069`、`_handle_start_failure` `:3297`）与恢复阶段 helper（`_restore_paths`、`_assert_compatible_schema`、`_switch_item`）均可独立调用；`test_start_session_precheck_is_independent`、`test_restore_paths_and_schema_guard_are_independent`、`test_switch_item_renames_live_and_writes_journal` 直接断言前置与回滚效果通过。
- AC-008：TICK-VALID，re_verified。`tests/unit/test_t075_supervisor_fonts.py:165` 改用 `monkeypatch.setattr`，`# type: ignore[method-assign]` 已移除，断言未变；该用例在本轮 19 + 106 例复跑中通过。
- AC-009：TICK-VALID，trust_prior。本轴独立复测 AST 近似 McCabe 为 12 / 13 / 8 / 4 / 11（分类 helper 12），五目标函数均 < 15，数值与 `progress.md` / ADR 044 口径一致；106 例相关单元与契约级回归全绿。完整 `scripts/run_gates.sh` 与黑盒 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker 运行态与重建镜像，本轴未重跑，沿用 Round 1 已产出的门禁通过记录（`progress.md` 实施笔记）。

coverage = 9 / 9

verdict: PASS

## Round 3 (2026-11-24T07:11:51+08:00)

- round：3
- reviewed_at：2026-11-24T07:11:51+08:00
- 本轮变化：Round 2 后 `md_format.py` 仅对 Markdown / review 报告做格式化，无源码与测试语义变化；按相对 `3180cb90d72829eadadd481e73517f83c2188990` 的当前完整交付重新独立核实。

reviewed_scope: 0fb6d8c92a8c04e2

## Findings

本轮无新 finding（finding_id 跨轮全局续编，下一个为 `t107_code_f004`）。

## 结论

- 前轮 finding 复核（以当前 diff / 代码为准，不采信 `progress.md` 处置表）：
    - `t107_code_f001`（important，审计 created_at 漂移）：仍已消除。`src/backend/cbrowser/adapters/database/repository.py:847-856` 调用 `_record_operation_audit(..., sig_hash=sig_hash, now=now, extra={"version": new_version})`；helper 定义于 `:178-203`，`:201` 显式 `created_at=now`，`details` 由 `{"sig_hash": sig_hash}` 叠加 extra 合成（`:190-192`）。审计行不再回落到列默认值。
    - `t107_code_f002`（minor，`_switch_item` 死参数）：仍已消除。`scripts/restore_point.py:746-748` 签名为 `_switch_item(item, journal_path, journal, manifest)`，函数体 `:749-771` 无 `point` 引用，`point_has_dir` 仅用 `manifest` 与 `item["id"]`；调用点 `:805` 与 `tests/unit/test_t107_domain_boundaries.py` 均传 4 实参。
    - `t107_code_f003`（minor，`key_sha` 死变量）：仍已消除。`src/backend/cbrowser/adapters/database/extension_paths_migration.py:352` 为 `cid, ver = str(info["chromium_id"]), str(info["version"])`，入口不再计算未使用的 `key_sha`；分类 helper 内部自行读 `info["key_sha256"]`（`:316`）。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大（按降级规则仅列路径与行数，不进 finding 表）：`src/backend/cbrowser/supervisor/core.py` 3675 行、`src/backend/cbrowser/adapters/database/repository.py` 3081 行、`src/backend/cbrowser/services/profile_service.py` 2366 行、`scripts/restore_point.py` 867 行、`src/backend/cbrowser/adapters/database/extension_paths_migration.py` 648 行，均超阈值但属本 task 拆分重构净增且 diff 未给不可拆硬约束，与 Round 2 一致，仅作提示。新测试 `tests/unit/test_t107_domain_boundaries.py` 373 行，未达测试 600 行阈值。
    - 圈复杂度：本轮 AST 近似 McCabe 实测 `profile_service.update_profile` 11 / `repository.update_profile` 11 / `supervisor.start_profile` 6 / `restore_point` 4 / `_match_legacy_entry` 10 / `_classify_managed_candidates` 10，均 < 15（与 Round 2 同为 < 15，计数器实现差异导致数值略有不同）；无复杂度 finding。
    - 范围外观察：无。格式化仅触及 Markdown / review 报告，未改变任何源码、测试或对外契约；`task.md` 九条 AC 仍全部为 `- [x]`。
- 总体判断：前轮唯一 blocker 及两条 minor 经当前代码独立核实仍全部消除，本轮未引入新问题；93 例相关单元回归全绿，六目标函数 CC 均 < 15，本轴无未解决 critical / important → PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。当前 `services/profile_service.py` 三类校验 helper 与 `repository.update_profile` 的版本跃迁 / 同值不抬升 / 快照 / 审计 / 幂等重放 / 异常映射分支逐段核对锚点一致，`_record_operation_audit(..., created_at=now)` 无漂移；复跑 `test_domain_and_repository`、`test_repository_idempotency`、`test_t056_references` 全绿。
- AC-002：TICK-VALID，re_verified。`start_profile` 阶段 helper 顺序（前置→意图→陈旧清理→绑定→装配→容器→收敛→提交/失败收尾）与锚点一致，`_start_failure_reason` 映射与事件/端口收尾等价；`test_supervisor_start_conflicts`、`test_supervisor_startup_recovery`、`test_t075_supervisor_fonts` 全绿。
- AC-003：TICK-VALID，re_verified。`_restore_paths`/`_assert_compatible_schema`/`_sweep_stale_staging`/`_stage_restore_items`/`_switch_item`（`scripts/restore_point.py:746`）与锚点逐段等价，journal、`_fsync_dir` 与失败回滚保留；`test_t066_restore_point` 全绿，恢复点格式与退出码未变。
- AC-004：TICK-VALID，re_verified。`_classify_managed_candidates`（`src/backend/cbrowser/adapters/database/extension_paths_migration.py:314`）四类结论与 `_match_legacy_entry`（`:342-387`）文案逐项等价，死变量 `key_sha` 已移除；`test_t104_extension_paths_migration` 全绿。
- AC-005：TICK-VALID，re_verified。`_resolve_platform_binding`/`_validate_patch_references`/`_validate_patch_extensions` 为可独立调用单元，`update_profile` 编排仅调用、不再内联三类判断；`test_t107_domain_boundaries.py` 三条直测通过。
- AC-006：TICK-VALID，re_verified。`_profile_config_from_model`/`_apply_config_to_model` 以 `ProfileConfig.model_fields` 为唯一字段来源，旧 22 字段手工清单已删除；`test_config_orm_projection_covers_every_config_field` 对读写全字段断言通过。
- AC-007：TICK-VALID，re_verified。启动与恢复阶段 helper 均可独立调用；`test_start_session_precheck_is_independent`、`test_restore_paths_and_schema_guard_are_independent`、`test_switch_item_renames_live_and_writes_journal` 直接断言前置与回滚效果通过。
- AC-008：TICK-VALID，re_verified。`tests/unit/test_t075_supervisor_fonts.py:165` 改用 `monkeypatch.setattr`，`# type: ignore[method-assign]` 已移除，断言未变；该用例在本轮 93 例复跑中通过。
- AC-009：TICK-VALID，trust_prior。本轴 AST 近似 McCabe 复测 11 / 11 / 6 / 4 / 10 / 10，六函数均 < 15，93 例相关单元回归全绿；完整 `scripts/run_gates.sh` 与黑盒 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker 运行态与重建镜像，本轴未重跑，沿用 Round 1/2 已产出的门禁通过记录（`progress.md` 实施笔记 / ADR 044）。

coverage = 8 / 9

verdict: PASS
