# Task review t104（reviewer_focus: 测试）

- task：`t104_managed_extensions_and_bitwarden_passkey`
- spec：`docs/tasks/t104_managed_extensions_and_bitwarden_passkey/task.md`
- diff_anchor：`41a4a3e848e673007090e4489beb0fbdb7ee5765`
- target：`git diff 41a4a3e848e673007090e4489beb0fbdb7ee5765`
- round：1
- reviewed_at：2026-11-23T01:40:12+08:00

## Findings

### t104_test_f001 - 0017 迁移阻断用例 `ambiguous_candidates` 重生新密钥导致误走 `缺失` 分支，且所有阻断用例未校验报错对象与分类

- 严重度：important
- 锚点：AC-002（迁移前扫描精确区分空列表、可验证映射、缺失与歧义；缺失、歧义或无法保持 Chromium 扩展 ID 连续性的条目指名 Profile 与版本 fail-before-write 阻断）
- 位置：`tests/unit/test_t104_extension_paths_migration.py:401-469`（`test_blockers_fail_before_write_with_zero_db_mutation`）
- 问题：
    1. `scenario == "ambiguous_candidates"`（第 401–430 行）第 402 行先调用 `_build_legacy_and_managed(tmp_path, key_name="same", ext_name="SameExt", version="1.0.0")` 生成第 1 对 RSA 密钥并写入 `tmp_path/same.pem`；第 406 行又以相同目录和 `name="same"` 再次调用 `_generate_rsa_pub_der(tmp_path, "same")`（`tests/unit/test_t104_extensions_manifest.py:24-42`），`openssl genrsa` 覆盖生成了**另一对完全不同的密钥**（实测 `cid1=ohpcjjemfboljpfpjoaagdgflfiodjfc`，`cid2=lgbelehiloiaapefojdlhiapnoljdmcl`）。随后第 408 行 `pkg2`（`2.0.0`）与第 423 行 `legacy_v3`（`3.0.0`）均使用 `cid2`，导致目录中仅存在 1 个 `cid2` 资产，`audit_extension_paths_database` 在 `src/backend/cbrowser/adapters/database/extension_paths_migration.py:312-325` 实际命中的是 `(分类=缺失)` 而非 `(分类=歧义)`（实测阻塞输出为 `missing verified managed asset ... (分类=缺失)`），`歧义` 分支与同目录多候选 / 多路径同 `chromium_id`（`seen_cids`）分支均未获实际测试覆盖。
    2. 第 466 行仅用裸 `with pytest.raises(RuntimeError):`，未对 `exc.value` 做任何断言，既未区分 `缺失` / `歧义` / `连续性` 分类，也未校验报错中是否明确指名 Profile（`p1`）与快照版本（`version 1`）。
- 建议：在 `ambiguous_candidates` 中复用 `_build_legacy_and_managed` 已写盘的 `same.der`（或新增独立的同密钥多版本夹具）确保 `1.0.0` 与 `2.0.0` 共享同一 `chromium_id`，并补测同一快照中多路径映射同一 `chromium_id` 的歧义分支；同时把 `pytest.raises(RuntimeError)` 改为按 `scenario` 精确断言 `Profile ID`、对应版本标签（或当前行标签）以及 `分类=缺失` / `分类=歧义` / `连续性` 关键词。

### t104_test_f002 - `SupervisorCore` 扩展预检失败测试使用 `# type: ignore[method-assign]` 且 mock 掉被测对象自身的 `report_terminal_observation`

- 严重度：important
- 锚点：AC-002 / 危险模式扫描（test 文件加 `# type: ignore` 静默类型错误、mock 自己类的关键副作用）
- 位置：`tests/unit/test_t104_supervisor_and_runner.py:274`（`test_supervisor_core_preflight_refuses_corrupt_bound_extension`）
- 问题：该测试已通过 `httpx.MockTransport(_handler)` 注入控制面 HTTP 传输桩，却仍在第 274 行对被测实例 `core` 直接赋值 `core.report_terminal_observation = AsyncMock(return_value=True)  # type: ignore[method-assign]`，既在新增测试中引入 `# type: ignore` 静默错误，又绕过了 `SupervisorCore.start_profile` 在捕获 `ExtensionUnavailableError` 后调用 `report_terminal_observation` 向 API 上报 `observed_state="error"`、`reason="extension_unavailable"` 的真实副作用与状态路径（`src/backend/cbrowser/supervisor/core.py:3236-3258`）。
- 建议：移除 `core.report_terminal_observation` 的 `AsyncMock` 赋值与 `# type: ignore[method-assign]`，让真实 `report_terminal_observation` 经由既有 `httpx.MockTransport` 发出请求，并断言观测请求载荷包含 `observed_state == "error"` 与 `reason == "extension_unavailable"`。

### t104_test_f003 - 前端 `AC-003` 缺少编辑态回显/增量保存、移除扩展按钮及扩展字段 `hasRuntimeConfigChange` 用例

- 严重度：minor
- 锚点：AC-003（新建与编辑表单默认隐藏或禁用扩展选择器、增删多个受管扩展、配置保存、回显、待应用提示）
- 位置：`src/frontend/src/features/profiles/ProfileForm.test.tsx:917-1026`、`src/frontend/src/features/profiles/profile_field_diff.test.ts:25-85`
- 问题：
    1. `ProfileForm.test.tsx:917-1026` 仅以 `mode="create"` 验证了默认隐藏、勾选显示风险提示/自由模式提示、添加两个扩展、同 ID 冲突禁用、上移与内联上传；未测试 `ProfileExtensionsSelector.tsx:215` 的移除操作（`ext-remove-*`）与下移操作（`ext-move-down-*`），也未覆盖 `mode="edit"` 下 `allow_extensions: false` 默认隐藏、`allow_extensions: true, extension_ids: [...]` 重开回显（`ProfileForm.tsx:97-98`），以及编辑态修改/关闭扩展后经 `diffProfileValues` 仅提交变更字段并回显的流程。
    2. `profile_field_diff.test.ts:25-85` 仅将 `extension_ids` 用于 `diffProfileValues` 数组相等性断言，未显式断言 `classifyProfileField("allow_extensions") === "runtime"`、`classifyProfileField("extension_ids") === "runtime"` 以及仅变更 `allow_extensions` / `extension_ids` 时 `hasRuntimeConfigChange` 返回 `true`。
- 建议：在 `ProfileForm.test.tsx` 补充 `mode="edit"` 扩展回显、点击 `ext-remove-*` 移除扩展及编辑提交用例，并在 `profile_field_diff.test.ts` 补充 `allow_extensions` / `extension_ids` 的分类与 `hasRuntimeConfigChange` 断言。

### t104_test_f004 - `0017` 迁后快照缺少 `ProfileConfig` 严格校验及非空迁移幂等/在运态保持断言

- 严重度：minor
- 锚点：AC-002（迁移后快照兼容严格模型与非空场景幂等、保留运行绑定）
- 位置：`tests/unit/test_t104_extension_paths_migration.py:261-365`、`tests/unit/test_t104_extension_paths_migration.py:281`
- 问题：
    1. `tests/unit/test_t103_launch_args_migration.py:710,722` 因 `0016` 快照仍含已被 `t104` 移除的 `extension_paths` 而删除了 `ProfileConfig.model_validate(...)` 断言；但 `test_verified_mapped_upgrade_preserves_order_id_continuity_and_snapshots`（`test_t104_extension_paths_migration.py:261-365`）在迁至 `0017` 后仅检查单个字典键，未调用 `ProfileConfig.model_validate(...)` 验证携带 `allow_extensions=True, extension_ids=[...]` 的已迁移平铺/包装快照完全符合当前严格 `ProfileConfig` 契约，也未对非空映射场景执行二次 `command.upgrade(cfg, "head")` 幂等复验及在运态 `profile_runtimes` / `user_data_dir` 保留断言。
    2. `test_t104_extension_paths_migration.py:271-285` 含无用死分支 `... if False else ...`。
- 建议：在 `test_verified_mapped_upgrade_preserves_order_id_continuity_and_snapshots` 中对迁移后的 `v1["config"]` 与 `v2` 增加 `ProfileConfig.model_validate(...)` 与 `"extension_paths" not in ...` 断言、补充二次 `upgrade("head")` 幂等与在运态绑定保留检查，并清理第 281 行死表达式。

## 结论

- 改测方向复核：既有测试修改（`tests/integration/test_api_subprocess.py`、`tests/integration/test_t103_profile_cleanup_api.py`、`tests/unit/test_domain_and_repository.py`、`tests/unit/test_egress_plan_and_runner_sdk.py`、`tests/unit/test_t035_openapi_contract.py`、`tests/unit/test_t056_migrations.py`、`tests/unit/test_t069_strict_control_contracts.py`、`tests/unit/test_t089_wrapped_snapshot_migration.py`、`tests/unit/test_t099_native_color_scheme.py`、`tests/unit/test_t103_retire_options_and_runner.py`、`tests/unit/test_t103_launch_args_migration.py` 及前端 24 个测试夹具同步）均因 `extension_paths` 退役为 `allow_extensions`/`extension_ids`、`launch_stealth_persistent_context` 接管启动参数、`extensions` 路由组与 `0017` 迁移头变更而更新，不存在「迁就实现 bug」的改测；`test_t103_launch_args_migration.py` 删除 `test_0016_is_single_head` 与 `0016` 快照上的 `ProfileConfig.model_validate` 属于历史版本固定，其替代验证应由 `test_t104_extension_paths_migration.py` 补全（见 `t104_test_f004`）。
- 本轮新发现：4 条（important 2 条，minor 2 条）
- 未进表的提示：
    - `.scratch/t104_deploy_verify/verify_ac004.py` 中的双 Profile 隔离测试对比了关闭态 `p_off`（`allow_extensions=False`）与受管态 `p_mgr`（`allow_extensions=True`）及各自 Stream 容器，实证了未绑定资产在其他 Profile 与 Stream 容器不可见以及 `p_mgr` 重启后 `chrome.storage.local` 连续性；但未补充两个同时开启同一受管扩展的 Profile 间互相读写 `chrome.storage.local` 互不串用的真机交叉对照。
    - `tests/unit/test_t104_supervisor_and_runner.py:274` 的 `report_terminal_observation` mock 与 `# type: ignore[method-assign]` 写法沿用自既有 `tests/unit/test_t075_supervisor_fonts.py:165`（范围外历史测试暂未修改，后续可统一清理）。
- 总体判断：存在 2 条未解决 `important` finding（`t104_test_f001`、`t104_test_f002`）且 `AC-002` 判定 `TICK-VOID`，测试审查不通过。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已重跑 `tests/unit/test_t104_extensions_manifest.py`（4 passed）与 `tests/integration/test_t104_extensions_api.py`（4 passed），经由真实 FastAPI `create_app` + `TestClient` + 迁移 SQLite 库验证 CRX3/ZIP 上传校验、不可变资产 ID、图标与安全响应头、损坏/无 key/非法 manifest 拒绝及当前与运行中绑定版本 409 删除保护。
- AC-002：TICK-VOID，re_verified。虽重跑全量 unit/integration 通过（含 `tests/unit/test_t104_extension_paths_migration.py` 9 passed、`tests/unit/test_t104_supervisor_and_runner.py` 7 passed、`tests/integration/test_t104_extensions_api.py` 422 校验），但 `test_t104_extension_paths_migration.py:401-469` 中 `ambiguous_candidates` 实测误走 `缺失` 分支且 `pytest.raises(RuntimeError)` 未核验报错中的 Profile/版本/分类，同时 `test_t104_supervisor_and_runner.py:274` 存在 `# type: ignore[method-assign]` 并 mock 掉 `SupervisorCore.report_terminal_observation`（见 `t104_test_f001`、`t104_test_f002`）。
- AC-003：TICK-VALID，re_verified。已重跑 `src/frontend` 全套门禁（`design:lint` 0 error/0 warning、`design:check` clean、`check:api` 同步、`test:types` 通过、`vitest run` 88 files / 749 passed，含 `ProfileForm.test.tsx` 20 passed 与 `SettingsPage.test.tsx` 4 passed）及 `tests/unit/test_t058_profile_field_classification.py`、`tests/unit/test_a16_protocol_drift.py`，覆盖默认隐藏、风险提示、自由模式提示、多选排序上传与 OpenAPI/`profile_field_classification.ts` 同步（非阻塞增量覆盖缺口记为 `minor` `t104_test_f003`）。
- AC-004：TICK-VALID，trust_prior。本轮未在 Docker 内重建启动真机栈，依赖检查 `.scratch/t104_images.json` 及实施侧产物 `.scratch/t104_deploy_verify/verify_ac004.py`、`ac004_results.json`、`verify_migration_and_restore.py`、`migration_restore_results.json`（实测覆盖默认关态、`[tiny, ext_two]` 双受管并发、Free 模式 GTK3 Load unpacked 跨重启持久、切受管拒载、切回关态停用、Stream 零挂载与 `0016->0017`/`restore_point.py` 连续性）。
- AC-005：TICK-VALID，trust_prior。本轮未在 Docker 内拉起 Vaultwarden/代理栈，依赖检查 `.scratch/t104_images.json` 及实施侧产物 `.scratch/t104_deploy_verify/verify_ac005.py`、`ac005_results.json`（实测加载官方 `bitwarden.crx` `2026.11.0`，验证直接 TLS/公网阻断、认证 HTTP CONNECT 代理、Vaultwarden 登录同步及 WebAuthn `navigator.credentials.create/get` 完成同 ID `6rZZrfDPSvOP6h5z4fYpXQ` Passkey 闭环）。

coverage = 3 / 5
建议合并前人工抽查 trust_prior 项

reviewed_scope: 6432fd60c46b328f

verdict: FAIL

## Round 2 (2026-11-23T02:35:01+08:00)

### 结论

- 前轮 finding 复核：
    - `t104_test_f001`：**已消除**。`tests/unit/test_t104_extension_paths_migration.py:408-467,503-509` 已在 `ambiguous_candidates` 复用 `same.der` 公钥构造共享同一 `chromium_id` 的 `1.0.0`、`2.0.0` 受管资产并由 `legacy_v3`（`3.0.0`）实际命中 `extension_paths_migration.py:314-321` 的 `(分类=歧义)` 分支，同时新增 `ambiguous_duplicate_cid_in_snapshot` 覆盖同快照多路径映射同 `chromium_id`（`seen_cids` 分支）；`expected_tokens` 对 7 个阻断场景均校验报错含 `p1`、`version 1` 与对应分类标签（`分类=缺失`、`分类=歧义`、`分类=无法保持扩展 ID 连续性`、`corrupt snapshot JSON`）。
    - `t104_test_f002`：**已消除**。`tests/unit/test_t104_supervisor_and_runner.py:205-294` 已移除 `core.report_terminal_observation = AsyncMock(...)` 与 `# type: ignore[method-assign]`；真实 `SupervisorCore.report_terminal_observation` 经 `httpx.MockTransport` 发送 `/runtimes/observed` 请求，断言 `observed_payloads[0]["observed_state"] == "error"`、`observed_payloads[0]["reason"] == "extension_unavailable"` 且 `adapter.start_browser_container.assert_not_awaited()`。
    - `t104_test_f003`：**已消除**。`src/frontend/src/features/profiles/ProfileForm.test.tsx:1032-1116` 新增编辑态（`mode="edit"`）回显、`ext-move-down-*`、`ext-remove-*` 及只提交 `{ extension_ids: [assetA.id] }` / `{ allow_extensions: true }` 增量 diff 用例；`src/frontend/src/features/profiles/profile_field_diff.test.ts:27-109` 补充 `classifyProfileField`（`allow_extensions` / `extension_ids` 均为 `runtime`）与 `hasRuntimeConfigChange` 显式断言。
    - `t104_test_f004`：**已消除**。`tests/unit/test_t104_extension_paths_migration.py:262-368` 已清理死分支 `if False else`，增加非空映射 DB 二次 `command.upgrade(cfg, "head")` 幂等验证、迁后 `v1["config"]` 与 `v2` 的 `ProfileConfig.model_validate(...)` 严格校验及 `user_data_dir` / `current_config_version` / `profile_runtimes` 保持断言。
- 改测方向复核：Round 2 新增/调整测试均服务于消除 Round 1 测试缺陷或覆盖代码缺陷修复（ZIP 炸弹流式上限 `test_t104_extensions_manifest.py:206-269`、自由模式仅开 `allow_extensions` 与 404 回归 `test_t104_extensions_api.py:307-332`、资产删除/导入/绑定并发 TOCTOU `test_t104_extensions_api.py:335-407`、Used by 不暴露 `#display_number` `SettingsPage.test.tsx:139-270`、`extensionKeys.all` 失效 `useProfilesQuery.test.tsx:1583-1643`、`.staging-*` 跳过与容器优雅停止 `test_t104_supervisor_and_runner.py:456-552`）；全量 test diff 危险模式扫描无命中。
- 本轮新发现：0 条（critical 0 条，important 0 条，minor 0 条）
- 未进表的提示：
    - Round 1 提及的双活跃受管扩展 Profile 存储隔离已由 `.scratch/t104_deploy_verify/verify_ac004.py:470-490` 与刷新后的 `ac004_results.json` 补齐验证。
    - 既有范围外测试 `tests/unit/test_t075_supervisor_fonts.py:165` 仍保留历史 `report_terminal_observation` mock 写法，属范围外非本次修改，维持后续统一清理观察项。
- 总体判断：Round 1 全部 4 条 finding 均已实质消除，代码修复对应回归测试完整且无危险模式，契约、前后端全量门禁与协议导出只读校验全通过，全部 5 条 AC 判定 `TICK-VALID`，测试审查通过。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已独立复核并重跑 `tests/unit/test_t104_extensions_manifest.py`（5 passed，含新增 `test_unpack_rejects_zip_bomb_with_forged_file_size`）与 `tests/integration/test_t104_extensions_api.py`（6 passed，含并发 TOCTOU 用例 `test_concurrent_delete_import_and_profile_binding_preserve_invariants`），覆盖 CRX3/ZIP 校验、不可变 ID、图标头、422 拒绝、409 保护与竞态不变式。
- AC-002：TICK-VALID，re_verified。已独立复核并重跑 `tests/unit/test_t104_extension_paths_migration.py`（10 passed）、`tests/unit/test_t104_supervisor_and_runner.py`（7 passed）、`tests/integration/test_t104_extensions_api.py`（6 passed）及后端全量 `tests/unit`（2529 passed, 13 skipped）与 `tests/integration`（229 passed, 18 skipped）；`t104_test_f001` / `t104_test_f002` / `t104_test_f004` 已消除，并覆盖 `PATCH {"allow_extensions": true}`、404 与 422 回归。
- AC-003：TICK-VALID，re_verified。已独立复核并重跑前端全套门禁（`design:lint` 0 error / 0 warning、`design:check` clean、`check:api` exit 0、`test:types` pass、`vitest run --run` 88 files / 752 passed，含 `ProfileForm.test.tsx` 21 passed、`profile_field_diff.test.ts` 9 passed、`useProfilesQuery.test.tsx` 29 passed、`SettingsPage.test.tsx` 4 passed）及 `test_t058_profile_field_classification.py`、`test_a16_protocol_drift.py` 与 4 份后端协议 `--check`、`contract` 测试（388 passed, 1 skipped）；`t104_test_f003` 已消除。
- AC-004：TICK-VALID，trust_prior。本轮未在 Docker 内自行重建拉起容器栈，依赖核验重建后刷新的 `.scratch/t104_images.json` 及 `.scratch/t104_deploy_verify/{verify_ac004.py,ac004_results.json,verify_migration_and_restore.py,migration_restore_results.json}`（覆盖四态隔离、Free 模式 Load unpacked 持久、`0016->0017` 与 `restore_point` 连续性及 `p_mgr`/`pid_free` 双向 `chrome.storage.local` 隔离 `isolated-secret-A` / `isolated-secret-B`）。
- AC-005：TICK-VALID，trust_prior。本轮未在 Docker 内自行拉起 Vaultwarden/代理栈，依赖核验重建后刷新的 `.scratch/t104_images.json` 及 `.scratch/t104_deploy_verify/{verify_ac005.py,ac005_results.json}`（在重建镜像内受管加载官方 `bitwarden.crx`，实证直连阻断、认证代理 `proxy_auth_checked=114`、Vaultwarden 登录同步及 WebAuthn `navigator.credentials.create/get` 同 ID `juZvVKBATK6_3MIrUfvJOQ` Passkey 闭环）。

coverage = 3 / 5
建议合并前人工抽查 trust_prior 项

reviewed_scope: 0ce7fd1e4cb519c9

verdict: PASS
