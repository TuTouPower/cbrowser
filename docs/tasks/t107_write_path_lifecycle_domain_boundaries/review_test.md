# Task review t107（reviewer_focus: 测试）

- task：`t107_write_path_lifecycle_domain_boundaries`
- spec：`docs/tasks/t107_write_path_lifecycle_domain_boundaries/task.md`
- diff_anchor：`3180cb90d72829eadadd481e73517f83c2188990`
- target：`git diff 3180cb90d72829eadadd481e73517f83c2188990`
- round：1
- reviewed_at：2026-11-24T06:20:12+08:00

## Findings

### t107_test_f001 - AC-005 三类写路径校验无任何直接调用测试，与可测试性声明矛盾

- 严重度：important
- 锚点：AC-005（三类校验各自可独立调用并单独断言；可测试性声明承诺「AC-005/007 由新拆分单元的直接调用断言」）
- 位置：`tests/unit/test_t107_domain_boundaries.py:1-232`（全文件缺失）；新拆方法位于 `src/backend/cbrowser/services/profile_service.py:753`（`_resolve_platform_binding`）、`:787`（`_validate_patch_references`）、`:793`（`_validate_patch_extensions`）
- 问题：`update_profile` 新抽出的三个校验方法（平台/字体绑定、分组与代理引用、扩展白名单）在新增测试文件中零引用。全量 grep `tests/` 确认这三个方法名没有任何测试直接调用。新增文件只覆盖 AC-006（`test_config_orm_projection_covers_every_config_field`）与 AC-007（start precheck / failure reason / restore paths / schema guard / switch item），完全跳过 AC-005。三类校验的**行为**虽经既有 `update_profile` 集成测试（`tests/integration/test_profile_patch_semantics.py`）间接触达，但 AC-005 的独立可调用性与「单独断言」这一验收点没有任何测试证据，打勾缺少有效测试支撑，属测试假绿。
- 建议：在 `tests/unit/test_t107_domain_boundaries.py` 增加三个新单元的直测：直接调用 `_resolve_platform_binding` 覆盖平台切换重绑/无可用集失败封闭/同平台字体变更；直接调用 `_validate_patch_references` 覆盖分组与代理引用校验及显式 null 清除不查库；直接调用 `_validate_patch_extensions` 覆盖 `extension_ids`/`allow_extensions` 两条触发路径。断言须触达副作用/异常，不得用恒真或 mock 被测逻辑。

## 结论

- 前轮 finding 复核：无（Round 1）
- 改测方向复核：本轮唯一既有测试改动是 `tests/unit/test_t075_supervisor_fonts.py:165` 把 `core.report_terminal_observation = AsyncMock(...)  # type: ignore[method-assign]` 换成 `monkeypatch.setattr`，系 spec 范围明确要求，断言语义未变，非迁就实现；无「迁就实现」改测
- 本轮新发现：1 条
- 未进表的提示：AC-007 仅直接断言部分新阶段（前置 precheck、失败原因、恢复路径/schema、单项切换），未直测 `_assert_start_intent`/`_bind_runtime_instance`/`_prepare_start_artifacts`/`_stage_*` 等；这些阶段经既有 start/restore 回归间接覆盖，属「覆盖可更广」的 minor 扩展建议，不阻断，不进 finding 表。无恒真断言、无 `.skip`/`.only`、未 mock 被测逻辑本身。
- 总体判断：AC-005 打勾缺少其声明的直接调用测试（important），阻断 PASS；AC-006/007 新测试真实触达生产逻辑，行为不变 AC 回归通过。
- 系统性 follow-up：无
- reviewed_scope: 6f5e2449f967f357

### AC 复验方式

- AC-001：TICK-VALID，re_verified。重跑 `test_domain_and_repository.py`、`test_repository_idempotency.py`、`test_t056_*`、`test_profile_patch_semantics.py` 等共 116 例全绿，写路径既有行为回归通过。
- AC-002：TICK-VALID，re_verified。重跑 `test_supervisor_core.py`、`test_supervisor_start_conflicts.py`、`test_t075_supervisor_fonts.py`、`test_t049_supervisor_restore.py` 全绿，启动既有行为回归通过。
- AC-003：TICK-VALID，re_verified。重跑 `test_t066_restore_point.py`、`test_t049_supervisor_restore.py` 全绿，恢复点既有行为与格式回归通过。
- AC-004：TICK-VALID，re_verified。重跑 `test_t104_extension_paths_migration.py` 全绿，且新增 `test_managed_candidate_classification` 四分支直测 `_classify_managed_candidates`。
- AC-005：TICK-VOID，re_verified。全量 grep `tests/` 与通读新增文件确认三个新拆校验方法零测试引用；可测试性声明承诺的「新单元直接调用断言」未交付。
- AC-006：TICK-VALID，re_verified。`test_config_orm_projection_covers_every_config_field` 遍历 `ProfileConfig.model_fields` 双向断言 `_profile_config_from_model`/`_apply_config_to_model` 覆盖全部配置字段。
- AC-007：TICK-VALID，re_verified。`test_start_session_precheck_is_independent` 等四项直接调用新阶段断言前置条件与切换/日志效果，回滚效果另由既有 `test_t066_restore_point` 回归。
- AC-008：TICK-VALID，trust_prior。diff 复核确认仅替换 mock 写法、断言未变且新测试全绿；类型检查工具链本机不可用，依赖实施侧 `scripts/run_gates.sh` 类型门禁通过证据。
- AC-009：TICK-VALID，trust_prior。本机未重跑全量门禁与 Docker 黑盒 E2E，依赖实施侧 `scripts/run_gates.sh` 与 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 全绿声明；本机已重跑后端 unit/integration 相关套件全绿。

coverage = 7/9

verdict: FAIL

## Round 2 (2026-11-24T07:04:17+08:00)

### Findings

本轮新发现：0 条。

### 前轮 finding 复核

- t107_test_f001：已消除。相对 `3180cb90d72829eadadd481e73517f83c2188990` 的 diff 新增 `tests/unit/test_t107_domain_boundaries.py:302-373` 三例直测，分别直接调用生产方法 `ProfileService._validate_patch_references`（`src/backend/cbrowser/services/profile_service.py:787`）、`_validate_patch_extensions`（`:793`）、`_resolve_platform_binding`（`:753`）。独立核实：三例重跑全绿；coverage 确认 `profile_service.py:753-791`、`:793-805` 实际执行（含 `_validate_references`/`_validate_extensions`/`_validate_font_set_binding`）。断言落在具体副作用与异常上（`repo.group_calls`/`proxy_calls`、`catalog.calls`、`asset_calls`、`patch_dict["font_set_id"]`、`exc.value.details` 的 loc、`pytest.raises`），非恒真；Fake 仅替代 DB / 字体目录 / 扩展目录边界，`set_font_catalog`/`set_extension_catalog` 为生产注入点，未 mock 被测方法本身。结论以 diff 与代码/测试为准，未采信处置表。

### 结论

- 改测方向复核：无新增「迁就实现」的既有测试改动。
- 本轮新发现：0 条。
- 未进表的提示：`_resolve_platform_binding` 中无字体根目录分支（`profile_service.py:771`）与 `_validate_font_set_binding` 的三条异常分支未被三例直测直接覆盖，属「覆盖可更广」minor 扩展建议，不阻断；AC-007 的部分启动阶段仍由既有 start/restore 回归间接覆盖，维持 Round 1 判断。
- 总体判断：前轮唯一 blocker 已用真实直测消除，AC-005 打勾现有有效测试支撑；本机重跑相关单元/集成共 148 例全绿，无未解决 critical/important，AC 复验全部 TICK-VALID。
- 系统性 follow-up：无
- reviewed_scope: 29d45aeaded51059

### AC 复验方式

- AC-001：TICK-VALID，re_verified。重跑 `test_domain_and_repository.py`、`test_repository_idempotency.py`、`test_t056_*.py`、`test_profile_patch_semantics.py` 全绿，写路径元数据/版本/快照/分组代理引用/扩展白名单/幂等行为回归通过。
- AC-002：TICK-VALID，re_verified。重跑 `test_supervisor_core.py`、`test_supervisor_start_conflicts.py`、`test_t075_supervisor_fonts.py`、`test_t049_supervisor_restore.py` 全绿，启动幂等/force/阻塞/意图/绑定/装配/收敛/失败收尾行为回归通过。
- AC-003：TICK-VALID，re_verified。重跑 `test_t066_restore_point.py`、`test_t049_supervisor_restore.py` 全绿；新增 `test_restore_paths_and_schema_guard_are_independent`、`test_switch_item_renames_live_and_writes_journal` 直测恢复路径、schema stamp 校验与原子切换副作用。
- AC-004：TICK-VALID，re_verified。重跑 `test_t104_extension_paths_migration.py` 全绿；`test_managed_candidate_classification` 四分支直测 `_classify_managed_candidates` 分类结论。
- AC-005：TICK-VALID，re_verified。三例直测分别调用 `_validate_patch_references`、`_validate_patch_extensions`、`_resolve_platform_binding`；coverage 确认三段生产代码实际执行，断言落在 repo/catalog 调用记录、返回值与异常 details，Fake 仅在系统边界替代，无恒真与被测逻辑 mock；本轮 3 例重跑全绿。
- AC-006：TICK-VALID，re_verified。`test_config_orm_projection_covers_every_config_field` 双向遍历 `ProfileConfig.model_fields` 断言 `_profile_config_from_model` 与 `_apply_config_to_model` 覆盖全部字段，重跑通过。
- AC-007：TICK-VALID，re_verified。`test_start_session_precheck_is_independent`、`test_start_failure_reason_mapping` 与恢复阶段直测触达新阶段；`_assert_start_intent`/`_bind_runtime_instance`/`_stage_*` 等由既有 start/restore 回归间接覆盖（minor 扩展建议，不阻断）。
- AC-008：TICK-VALID，trust_prior。diff 复核确认仅把 `# type: ignore[method-assign]` 赋值改为 `monkeypatch.setattr`，断言语义不变且 `test_t075_supervisor_fonts.py` 重跑通过；类型门禁本机未执行，依赖实施侧 gate 证据。
- AC-009：TICK-VALID，trust_prior。本机重跑后端单元/集成相关套件共 148 例全绿；全量 `scripts/run_gates.sh`、黑盒 E2E 与 CC\<15 复测依赖实施侧门禁证据，未在本机执行。

coverage = 9/9

verdict: PASS

## Round 3 (2026-11-24T07:15:42+08:00)

### Findings

本轮新发现：0 条。

### 前轮 finding 复核

- t107_test_f001：仍已消除。相对 `3180cb90d72829eadadd481e73517f83c2188990` 的完整交付中，`tests/unit/test_t107_domain_boundaries.py:302-373` 三例直测仍在：`test_validate_patch_references_directly` 调用生产方法 `ProfileService._validate_patch_references`（`src/backend/cbrowser/services/profile_service.py`）、`test_validate_patch_extensions_directly` 调用 `_validate_patch_extensions`、`test_resolve_platform_binding_directly` 调用 `_resolve_platform_binding`。本轮独立重跑相关单元/集成共 148 例全绿，三例均通过；断言落在 repo/catalog 调用记录、返回值与异常 details，Fake 仅替代 DB / 字体目录 / 扩展目录边界，未 mock 被测逻辑。Round 2 后仅 markdown 报告经格式化，测试与源码无语义变化，f001 修复保持有效。

### 结论

- 改测方向复核：无新增「迁就实现」的既有测试改动；唯一既有测试改动 `tests/unit/test_t075_supervisor_fonts.py:165` 为 spec 明确要求的 mock 写法替换，断言语义未变。
- 本轮新发现：0 条。
- 未进表的提示：本轮唯一变化是 md_format.py 对 Markdown/review 报告的格式化，`docs/blueprint/architecture.md`、`docs/specs/*.md`、`task.md` 仅排版与打勾变化，无源码或测试语义变化；危险模式扫描（恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`、`# type: ignore`、mock 被测逻辑、阈值掩盖、条件跳过）在测试 diff 中零命中。
- 总体判断：当前 scope 指纹实算为 `0fb6d8c92a8c04e2`，与派审锚点一致；148 例相关测试全绿，前轮唯一 blocker 已消除且无新 blocker，AC 复验全部 TICK-VALID，判 PASS。
- 系统性 follow-up：无
- reviewed_scope: 0fb6d8c92a8c04e2

### AC 复验方式

- AC-001：TICK-VALID，re_verified。重跑 `test_domain_and_repository.py`、`test_repository_idempotency.py`、`test_t056_*.py`、`test_profile_patch_semantics.py` 全绿，写路径元数据/版本/快照/分组代理引用/扩展白名单/幂等行为回归通过。
- AC-002：TICK-VALID，re_verified。重跑 `test_supervisor_core.py`、`test_supervisor_start_conflicts.py`、`test_t075_supervisor_fonts.py`、`test_t049_supervisor_restore.py` 全绿，启动幂等/force/阻塞/意图/绑定/装配/收敛/失败收尾行为回归通过。
- AC-003：TICK-VALID，re_verified。重跑 `test_t066_restore_point.py`、`test_t049_supervisor_restore.py` 全绿；`test_restore_paths_and_schema_guard_are_independent`、`test_switch_item_renames_live_and_writes_journal` 直测恢复路径、schema stamp 校验与原子切换副作用。
- AC-004：TICK-VALID，re_verified。重跑 `test_t104_extension_paths_migration.py` 全绿；`test_managed_candidate_classification` 四分支直测 `_classify_managed_candidates` 分类结论。
- AC-005：TICK-VALID，re_verified。三例直测直接调用 `_validate_patch_references`、`_validate_patch_extensions`、`_resolve_platform_binding`，断言落在 repo/catalog 调用记录、返回值与异常 details，Fake 仅在系统边界替代，无恒真与被测逻辑 mock；本轮重跑全绿。
- AC-006：TICK-VALID，re_verified。`test_config_orm_projection_covers_every_config_field` 双向遍历 `ProfileConfig.model_fields` 断言 `_profile_config_from_model` 与 `_apply_config_to_model` 覆盖全部字段，重跑通过。
- AC-007：TICK-VALID，re_verified。`test_start_session_precheck_is_independent`、`test_start_failure_reason_mapping` 与恢复阶段直测触达新阶段；`_assert_start_intent`/`_bind_runtime_instance`/`_stage_*` 等由既有 start/restore 回归间接覆盖（minor 扩展建议，不阻断）。
- AC-008：TICK-VALID，trust_prior。diff 复核确认仅把 `# type: ignore[method-assign]` 赋值改为 `monkeypatch.setattr`，断言语义不变且 `test_t075_supervisor_fonts.py` 重跑通过；类型门禁工具本机不可用，依赖实施侧 gate 证据。
- AC-009：TICK-VALID，trust_prior。本机重跑后端单元/集成相关套件共 148 例全绿；全量 `scripts/run_gates.sh`、黑盒 E2E 与 CC\<15 复测依赖实施侧门禁证据，未在本机执行。

coverage = 9/9

verdict: PASS
