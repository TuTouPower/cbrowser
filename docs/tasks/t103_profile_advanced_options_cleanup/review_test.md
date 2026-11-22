# Task review t103（reviewer_focus: 测试）

- task：`t103_profile_advanced_options_cleanup`
- spec：`docs/tasks/t103_profile_advanced_options_cleanup/task.md`
- diff_anchor：`2d93270b2ae45922fcba865a49e9a183d61e89db`
- target：`git diff 2d93270b2ae45922fcba865a49e9a183d61e89db`
- round：1
- reviewed_at：2026-11-22T16:00:10+08:00

reviewed_scope: 939f20f613a5c96d

## Findings

### t103_test_f001 - 集成测试 mock 掉 `SupervisorCore.start_profile` 并在测试替身内伪造 `snapshot.json` 写盘

- 严重度：important
- 锚点：违反 `AC-004`（「Supervisor 新建实例向 API 拉取指定版本写 `snapshot.json`（含显式 `N` 版本启动与读取、协调器常规最新/应用重启选 `N+1`）」）；命中危险模式扫描「mock 误用」（mock 自己的类/关键副作用）及测试可信「生产逻辑可达」。
- 位置：`tests/integration/test_t103_profile_cleanup_api.py:279-357`
- 问题：在 `test_mute_audio_defaults_versioning_and_n_vs_n_plus_1_upgrade_supervisor_flow` 中，测试构建了匿名 `fake_core`，把 `start_profile` 替换为 `AsyncMock(side_effect=fake_start_profile)`（`tests/integration/test_t103_profile_cleanup_api.py:282-332`）。而在生产代码中，`control_server.py:218-262` 只向 API 拉取配置并反序列化为 `ProfileConfig`，真正组装 `ConfigVersionSnapshot`（含 `proxy_credential_revision`）并调用 `self._write_runtime_snapshot` 写入 `snapshot.json` 的生产逻辑位于 `SupervisorCore.start_profile`（`src/backend/cbrowser/supervisor/core.py:3008-3020`）。测试在 `fake_start_profile` 内部自行构造 `ConfigVersionSnapshot` 并执行 `(runtime_dir / "snapshot.json").write_text(...)`（第 290-299 行），随后第 341-345、353-357 行再读取该文件并断言其字段——实际验证的是测试替身自己的写盘结果，真实 `SupervisorCore.start_profile` 的写盘与快照构造链路完全未被触达。
- 建议：参考 `tests/unit/test_t035_proxy_runtime.py:545-700` 与 `tests/unit/test_t041_font_runtime.py:212-308`，构造真实 `SupervisorCore`（仅在 `DockerAdapter` / 容器启停与字体/网络外部边界打桩），通过 `create_control_app(core, sup_file)` 响应 `/supervisor/v1/profiles/start`，由真实 `SupervisorCore.start_profile` 写入 `snapshot.json` 并断言落盘文件内容。

### t103_test_f002 - 协调器针对 `N` vs `N+1` 选择最新配置版本的生产路径未测

- 严重度：important
- 锚点：违反 `AC-004`（「协调器常规最新/应用重启选 `N+1`」）。
- 位置：`tests/integration/test_t103_profile_cleanup_api.py:346-356`
- 问题：`tests/integration/test_t103_profile_cleanup_api.py:346` 注释声称「Apply / coordinator start of current latest version N+1=2」，但全测试从未实例化或调用 `RuntimeCoordinator`（`src/backend/cbrowser/api/runtime_coordinator.py:1265-1337` 的 `_reconcile_running` / `reconcile_profile_now`），而是由测试代码直接在 `sup_client.post("/supervisor/v1/profiles/start", ...)` 请求体中硬编码 `"config_version": 2`（第 347-351 行）。核查仓内既有协调器测试（`tests/unit/test_api_runtime_coordinator.py`、`tests/unit/test_t056_coordinator_errors.py`、`tests/unit/test_t056_proxy_password_impact.py`、`tests/integration/test_runtime_coordinator_integration.py`），在 `bound_version=N < current_config_version=N+1` 场景下均未校验协调器下发给 Supervisor `/supervisor/v1/profiles/start` 的 `config_version` 确实为 `N+1`，导致协调器版本选择逻辑在自动测试中存在零验证缺口。
- 建议：在 `tests/integration/test_t103_profile_cleanup_api.py`（接真实迁移后 DB 与 `ProfileService`）中实例化 `RuntimeCoordinator` 并对接 Supervisor mock/ASGI 传输，在绑定版本 `N=1` 且当前版本 `N+1=2`（包含常规最新启动与应用重启收敛）下调用 `reconcile_profile_now`，断言协调器实际发送的 `/supervisor/v1/profiles/start` 请求体中 `config_version == 2`。

### t103_test_f003 - 仅配置克隆未校验克隆体运行状态，含状态克隆仅写注释未实际调用

- 严重度：important
- 锚点：违反 `AC-004`（「及仅配置/含状态克隆后的运行意愿与绑定一致性」）。
- 位置：`tests/integration/test_t103_profile_cleanup_api.py:266-277,358-363`
- 问题：
    1. 第 266-277 行的仅配置克隆（`include_browser_state=False`）创建 `Clone-v2` 后只读取并断言了源环境 `p-upg` 的 `/runtime`（`desired_state == "running"`、`config_version == 1`），未读取并断言克隆体 `clone_data["id"]` 自身的 `/runtime`（`desired_state == "stopped"`、`observed_state == "stopped"`、`runtime_instance_id is None`、`config_version == 1`）及 `current_config_version == 1`。
    2. 第 358-363 行注释声明「State duplicate after stopping source also clones current N+1=2 and keeps source intact」，但测试仅调用 `POST /api/v1/profiles/p-upg/stop` 并断言 `desired_state == "stopped"` 后即终止，完全没有调用 `POST /api/v1/profiles/p-upg/duplicate`（`include_browser_state=True`），也未验证源环境仍处于 `observed_state="running"` / 绑定实例时含状态克隆被 409 拒绝、以及停止并解绑后含状态克隆成功且克隆体与源环境运行意愿/绑定/用户数据目录一致。
- 建议：在 `tests/integration/test_t103_profile_cleanup_api.py` 补全：（1）断言 `Clone-v2` 的 `/runtime` 满足 `desired_state == "stopped"`、`observed_state == "stopped"`、`runtime_instance_id is None`、`config_version == 1`；（2）在 `p-upg` 仍绑定运行实例时验证 `include_browser_state=True` 返回 409，随后将源环境停止并解绑（`observed_state="stopped"`、`runtime_instance_id=None`）并准备用户数据文件后执行 `include_browser_state=True` 克隆，断言克隆体继承 `N+1` 配置与用户数据、克隆体运行时为 `stopped/v1` 且源环境配置、历史版本与数据目录保持完整。

### t103_test_f004 - 替换 `t053` 默认值测试后丢失对在役非静音选项默认值的后端断言

- 严重度：minor
- 锚点：`AC-001` / `AC-002` 新建默认值回归覆盖（refactor 型改测保留既有有效覆盖）。
- 位置：`tests/integration/test_t053_profile_locale_api.py:50-51`、`tests/unit/test_t053_profile_locale.py:95-97`、`tests/integration/test_t103_profile_cleanup_api.py:88`
- 问题：`t103` 删除了 `test_t053_profile_locale.py` 的 4 个默认值测试与 `test_t053_profile_locale_api.py::test_create_defaults_humanize_and_portable_cookies`，注释称由 `test_t103_profile_cleanup_api.py` 承接，但新测试 `test_t103_profile_cleanup_api.py:84-90` 与 `test_t103_retire_options_and_runner.py:53-54` 仅断言了 `mute_audio is False`，未在后端单测/集成层继续断言在役默认值（`clipboard_sync=True`、`set_google_default=True`、`restore_session=True`、`capture_preview=True`、`geoip=True`、`locale="en-US"`、`timezone=None`）。（前端 `src/frontend/src/features/profiles/ProfileForm.test.tsx:217-223` 保留了前端表单提交默认值断言。）
- 建议：在 `tests/unit/test_t103_retire_options_and_runner.py` 与 `tests/integration/test_t103_profile_cleanup_api.py` 的默认创建响应中一并断言上述在役选项默认值。

### t103_test_f005 - `0016` 阻断测试未覆盖平铺（flat）快照与「需裁决」盘点分类直接断言

- 严重度：minor
- 锚点：`AC-002` / `AC-004` 盘点与阻断边界覆盖广度。
- 位置：`tests/unit/test_t103_launch_args_migration.py:227-396`
- 问题：`test_readonly_inventory_classifies_all_dispositions_and_language_matrix` 只校验了 `冗余` 与 `等价映射`，未直接断言 `audit_launch_args_database` 对未知参数/超枚举语言输出 `category == "需裁决"`；`test_unresolved_or_corrupt_entries_block_with_zero_writes` 中注入的快照全部为 `wrapped=True`（第 381 行），未覆盖 `wrapped=False` 的平铺阻塞/损坏快照及 `geoip=False` 下 `--lang` 与 `--accept-lang` 冲突或 `geoip=True` 下等价单语 `--accept-lang=en-US,en` 被 GeoIP 覆盖的场景。
- 建议：在 `test_t103_launch_args_migration.py` 增加对 `audit_launch_args_database` 返回 `需裁决` disposition 的直接断言，并在 `test_unresolved_or_corrupt_entries_block_with_zero_writes` 补充 `wrapped=False` 平铺快照与冲突语言组合用例。

## 结论

- 改测方向复核：既有测试修改与删除均对应规格明确退役的模块与字段，未见「迁就实现 bug」的弱化改测：`tests/unit/test_launch_args.py` 与 `tests/integration/test_profile_launch_args_api.py` 因 `cbrowser/launch_args.py` 与 `launch_args` 退役整文件删除（在役用例 `test_runtime_storage_defaults_target_uid_1000` 迁入 `tests/unit/test_domain_and_repository.py:546-552`）；`tests/unit/test_t056_migrations.py:324-418` 按 `0016` 增删列更新黄金 schema 差异集；`tests/unit/test_t089_wrapped_snapshot_migration.py:535-630` 保留了 `0014/0015` 字节一致断言并在 `0016` 校验 `mute_audio=False`；`tests/unit/test_t069_strict_control_contracts.py`、`tests/integration/test_api_subprocess.py`、`src/frontend/src/features/profiles/ProfileForm.test.tsx` 等均按新契约更新夹具并保留等价边界验证。但新增集成测试 `tests/integration/test_t103_profile_cleanup_api.py` 存在 3 项测试可信度与覆盖缺陷（`t103_test_f001`–`t103_test_f003`）。
- 本轮新发现：5 条（3 条 `important`，2 条 `minor`）。
- 未进表的提示：
    1. `tests/integration/test_t103_profile_cleanup_api.py:25-30` 跨目录从 `tests.unit.test_t103_launch_args_migration` 导入私有辅助函数 `_insert_profile` / `_insert_version`（建议后续收口或内聚，不违背核心可信度）。
    2. `src/frontend/src/features/profiles/ProfileForm.test.tsx:815-818` 仅直接断言 `en.formRestoreSessionHelp` / `zh.formRestoreSessionHelp` 词典常量，未像 `mute_audio` / `color_scheme` 一样在 DOM 中聚焦 `formRestoreSession` 的帮助按钮并验证渲染出的 Tooltip 文本。
    3. `.scratch/verify_ac005_inner.py:386-406` 在容器黑盒脚本中记录 `restore_session_matrix` 实测结果到 `AC005_RESULT` JSON 供人工/报告核对，脚本末尾未对 4 格恢复结果加 `assert`，且语言断言仅核对 `navigator.languages[0]`；不过 `progress.md` 记录了完整输出矩阵。
- 总体判断：AC-001 与 AC-002 的自动测试与契约门禁已独立复验通过，但 AC-004 的新增集成测试存在 `SupervisorCore.start_profile` 假替身写盘（`t103_test_f001`）、协调器 `N+1` 选择未测（`t103_test_f002`）及克隆运行意愿/含状态克隆未测（`t103_test_f003`）3 个 blocking finding，当前 `verdict: FAIL`。
- 系统性 follow-up：无（`task.py list` 已有 `t104` 承接扩展清理后改造，上述 3 项均属 `t103` 自身 `AC-004` 范围）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立重跑 `tests/unit/test_t103_retire_options_and_runner.py`、`tests/integration/test_t103_profile_cleanup_api.py`、`tests/unit/test_a16_protocol_drift.py`、`tests/unit/test_t058_profile_field_classification.py`、`tests/unit/test_t035_openapi_contract.py`、`tests/unit/test_t056_migrations.py`、`tests/unit/test_domain_and_repository.py`（均通过，含在全部修改/新增单测与集成测试 `179 passed` + `57 passed` 中）、前端全量 `npm test -- --run`（`88` 测试文件 / `747` 用例通过，含 `ProfileForm.test.tsx`）与 `npm run check:api` 通过，并全量 `rg` 确认 6 个无效字段已从 ORM、领域模型、DTO、OpenAPI、TS 生成类型、探针摘要与表单移除且 `POST/PATCH/PUT` 均返回 422 零写入。
- AC-002：TICK-VALID，re_verified。独立重跑 `tests/unit/test_t103_launch_args_migration.py`、`tests/unit/test_t103_retire_options_and_runner.py`、`tests/integration/test_t103_profile_cleanup_api.py`、`tests/integration/test_api_subprocess.py` 通过，确认只读盘点覆盖 `冗余`（含 17 项 Playwright 默认项、`--disable-translate`、`AutomationControlled`）与 `等价映射`（`--mute-audio` -> `mute_audio=True`、显式 `locale`/`geoip` 开关/重复 `--lang` 与 `--accept-lang` 规则），阻塞项 0 写入中止，新建默认 `mute_audio=False`，且彻底退役后提交 `launch_args` 返回 422；`task.md` 已登记完整裁决记录。
- AC-004：TICK-VOID，re_verified。虽独立重跑 `tests/unit/test_t103_launch_args_migration.py` 与 `tests/unit/test_t089_wrapped_snapshot_migration.py` 证实 `0016` 前向迁移阻断零写入、DDL/DML 故障整体回滚、`upgrade head` 幂等及平铺/包装快照重写成立，但独立复核并运行 `tests/integration/test_t103_profile_cleanup_api.py:266-363` 发现测试 mock 掉了 `SupervisorCore.start_profile` 并自行在替身内写入 `snapshot.json`（`t103_test_f001`）、硬编码 `config_version: 2` 绕过 `RuntimeCoordinator` 版本选择（`t103_test_f002`）、且未校验 `Clone-v2` 运行态并完全遗漏 `include_browser_state=True` 含状态克隆调用（`t103_test_f003`），现有自动化测试无法支撑 AC-004 后半段打勾。
- AC-005：TICK-VALID，trust_prior。[deploy] 在固定 arm64 `146.0.7680.177.3` 有头容器内的真实 Web 语言主备（`Accept-Language`/`navigator.languages` 与 `chrome://settings` 英文边界）、440Hz PulseAudio `cbrowser_sink.monitor` 静音全零 vs 有声对照与 `restore_session` 2x2 四格矩阵依赖实施方基于 `.scratch/prepare_migrated_muted_snap.py` 与 `.scratch/verify_ac005_inner.py` 的真实运行证据（`progress.md`）；测试审阅侧独立查证上述脚本实现并与重跑通过的 `tests/unit/test_t103_retire_options_and_runner.py::test_runner_injects_mute_audio_and_restore_session_without_dead_flags` 及 `ProfileForm.test.tsx:778-819` 中英文边界文案校验一致。
- AC-007：TICK-VALID，trust_prior。[deploy] 在本地 OrbStack 隔离拓扑下真实 `scripts/deploy.sh` 升级、未 `restore` 前回退拒绝、`deploy.sh restore` 恢复前导备份后再 `rollback` 至 `f1a2b3c4d5e6` 以及 6 容器旧镜像 Browser 接管与停启切换新镜像/`snapshot.json` 演练依赖实施方基于 `.scratch/verify_ac007.py` 与 `.scratch/verify_ac007_adoption.py` 的执行证据（`progress.md`）；测试审阅侧已独立核对两份演练脚本的断言覆盖与迁移兼容性单测。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: FAIL

## Round 2 (2026-11-22T19:04:36+08:00)

- task：`t103_profile_advanced_options_cleanup`
- spec：`docs/tasks/t103_profile_advanced_options_cleanup/task.md`
- diff_anchor：`2d93270b2ae45922fcba865a49e9a183d61e89db`
- target：`git diff 2d93270b2ae45922fcba865a49e9a183d61e89db`
- round：2
- reviewed_at：2026-11-22T19:04:36+08:00

reviewed_scope: 3eaff827b9e80146

### Findings

无新发现（0 条新增 finding）。

### 结论

- 前轮 finding 复核：
    - `t103_test_f001`（`important`）：**已消除**。`tests/integration/test_t103_profile_cleanup_api.py:133-145,257-270,355-559` 已彻底移除匿名 `fake_core` 与 `AsyncMock(side_effect=fake_start_profile)` 伪写盘替身，改为构造真实 `SupervisorCore` + `create_control_app`（仅在 Docker/容器边界使用 `FakeDockerAdapter` 子类 `_AdapterDouble` 并导入真实已校验字体集），实际触发 `SupervisorCore.start_profile` 向 API 拉取并经 `ProfileConfig` 校验写入 `runtime_dir / "snapshot.json"`（覆盖显式 `N=1` 与协调器 `N+1=2` 两次落盘及 `DockerAdapter._bound_snapshot_geometry` 兼容读取旧盘内快照）。
    - `t103_test_f002`（`important`）：**已消除**。`tests/integration/test_t103_profile_cleanup_api.py:435-449,536-557` 已实例化真实 `RuntimeCoordinator`（接入真实 `ProfileService` 与包装真实 Supervisor ASGI 传输的 `_RecordingSupervisorTransport`），在绑定 `config_version=1 < current_config_version=2` 条件下执行 `await coordinator.reconcile_profile_now("p-upg")`，断言协调器实际发送的 `/supervisor/v1/profiles/start` 请求体中 `config_version == 2`、落盘 `snapshot.json` 切换为 `version=2` 且 `/runtime` 收敛至 `config_version=2`。
    - `t103_test_f003`（`important`）：**已消除**。`tests/integration/test_t103_profile_cleanup_api.py:326-354,470-496` 已补全仅配置克隆 `Clone-v2` 的自身 `/runtime`（`stopped`/`stopped`/`None`/`config_version=1`）与源环境保留断言、在跑/绑定态发起 `include_browser_state=True` 克隆返回 `409` 拒绝断言，以及停机解绑后执行 `include_browser_state=True` 含状态克隆的 `201` 响应、独立 `user_data_dir` 与 `Cookies` 字节复制、克隆体 `stopped/v1` 运行态及源环境 `current_config_version=2` / 版本 `[1, 2]` / 原 `Cookies` 完整性断言。
    - `t103_test_f004`（`minor`）：**已消除**。`tests/unit/test_t103_retire_options_and_runner.py:53-68` 与 `tests/integration/test_t103_profile_cleanup_api.py:88-99` 已补齐对全部在役选项默认值（`mute_audio=False`、`clipboard_sync=True`、`set_google_default=True`、`restore_session=True`、`capture_preview=True`、`geoip=True`、`locale` 创建默认 `"en-US"` / 领域模型默认 `None`、`timezone=None`、`screen_width=1920`、`screen_height=1080`、`color_scheme="light"`、`extension_paths=[]`）的后端单元与 API 断言。
    - `t103_test_f005`（`minor`）：**已消除**。`tests/unit/test_t103_launch_args_migration.py:299-490,570-613` 新增 `test_readonly_inventory_marks_need_adjudication_on_conflicts_and_unknowns` 直接断言 `audit_launch_args_database` 输出 `category == "需裁决"` 与 `action == "block_migration"`；在 `p-geoip-accept-only` 覆盖 `locale=None, geoip=True` 下单 `--accept-lang` 提升；在 `test_unresolved_or_corrupt_entries_block_with_zero_writes` 补充 `wrapped=False` 平铺阻断/坏快照及有/无 GeoIP 语言冲突矩阵；并新增 `test_async_sqlite_migration_atomicity_and_retry` 验证 `sqlite+aiosqlite:///` 中途 DDL 故障回滚后零残留 `_alembic_tmp_*` 且重跑 `upgrade head` 成功。
- 改测方向复核：无「迁就实现」的改测；既有测试清理（如删除 `tests/unit/test_launch_args.py` 与 `tests/integration/test_profile_launch_args_api.py`、迁移 `test_runtime_storage_defaults_target_uid_1000` 至 `tests/unit/test_domain_and_repository.py:547-552`）均对应规格退役模块，且 Round 2 修复全部直接触达真实生产路径与真实边界条件。
- 本轮新发现：0 条。
- 未进表的提示：
    1. `tests/integration/test_t103_profile_cleanup_api.py:25-30` 跨目录从 `tests.unit.test_t103_launch_args_migration` 导入 `_insert_profile` / `_insert_version`（非阻断组织建议）。
    2. `src/frontend/src/features/profiles/ProfileForm.test.tsx:815-818` 直接断言 `en.formRestoreSessionHelp` / `zh.formRestoreSessionHelp` 词典常量（非阻断覆盖扩展提示；`mute_audio` 已覆盖聚焦 Tooltip DOM 渲染）。
- 总体判断：Round 1 全部 5 条 finding（含 3 条 `important`）均已基于 diff 与真实重跑验证消除，本轮无新 finding，全部非 `[deploy]` AC 自动化测试可信充分，`[deploy]` AC-005 / AC-007 有完整隔离真实演练与更新后的脚本断言支撑，`verdict: PASS`。
- 系统性 follow-up：无（扩展清理后接管改造已在现有 task `t104` 承接）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立重跑后端 `277 passed`（含 `tests/unit/test_t103_retire_options_and_runner.py`、`tests/integration/test_t103_profile_cleanup_api.py`、`tests/unit/test_a16_protocol_drift.py`、`tests/unit/test_t058_profile_field_classification.py`、`tests/unit/test_t035_openapi_contract.py`、`tests/unit/test_t056_migrations.py`、`tests/unit/test_domain_and_repository.py`、`tests/unit/test_t035_profile_domain.py` 等 27 个套件）与前端 `npm run check:api` + `npm test -- --run`（`tsc` + Vitest `88` 文件 / `747` 用例全通过），并全量 `rg` 确认 6 个无效字段已彻底移除且 `POST/PATCH/PUT` 提交均返回 422 零写入。
- AC-002：TICK-VALID，re_verified。独立重跑 `tests/unit/test_t103_launch_args_migration.py`、`tests/unit/test_t103_retire_options_and_runner.py`、`tests/integration/test_t103_profile_cleanup_api.py` 与 `tests/integration/test_api_subprocess.py`（均含在 `277 passed` 中）通过，验证只读盘点正确输出 `冗余`/`等价映射`/`需裁决` 分类（覆盖 17 项 Playwright 默认项、`--disable-translate`、`AutomationControlled`、`--mute-audio` 及有/无 `geoip`、`locale=None` 仅 `--accept-lang` 提升与冲突规则）、未决项零写入阻断、全量在役默认值（含 `mute_audio=False`）及退役 `launch_args` 提交返回 422。
- AC-004：TICK-VALID，re_verified。独立重跑 `tests/unit/test_t103_launch_args_migration.py`、`tests/unit/test_t089_wrapped_snapshot_migration.py`、`tests/unit/test_t054_migration.py`、`tests/unit/test_t056_migrations.py`、`tests/unit/test_api_runtime_coordinator.py`、`tests/integration/test_runtime_coordinator_integration.py` 与 `tests/integration/test_t103_profile_cleanup_api.py`（均含在 `277 passed` 中）通过，验证平铺/包装及损坏快照 fail-before-write 零写入、sync 与 `sqlite+aiosqlite` 中途 DDL/DML 故障整体回滚且零残留 `_alembic_tmp_*`、重跑 `upgrade head` 幂等无漂移、旧盘内快照容忍、真实 `SupervisorCore.start_profile` 按 `N=1`/`N+1=2` 落盘 `snapshot.json`、真实 `RuntimeCoordinator.reconcile_profile_now` 选择 `N+1=2` 以及仅配置克隆、运行中 409 拒绝与停机解绑后含状态克隆一致性。
- AC-005：TICK-VALID，trust_prior。[deploy] 固定 arm64 `146.0.7680.177.3` 有头容器内的 Web 主备语言（`Accept-Language`、`navigator.languages` 与 `chrome://settings` 英文边界）、440Hz 音源静音全零 vs 有声对照与 `restore_session` 2x2 四格行为依赖实施方在重建修复镜像后基于 `.scratch/prepare_migrated_muted_snap.py` 与 `.scratch/verify_ac005_inner.py` 重跑的真机结果（`progress.md`）；测试审阅侧已查证 `.scratch/verify_ac005_inner.py:399-415` 已补充全部四格与音视频/语言断言，并与重跑通过的 `tests/unit/test_t103_retire_options_and_runner.py` 及 `ProfileForm.test.tsx:778-819` 文案测试一致。
- AC-007：TICK-VALID，trust_prior。[deploy] 隔离 OrbStack 拓扑下真实 `scripts/deploy.sh` 升级、未 `restore` 前回退拒绝、`deploy.sh restore` 恢复升级前数据库备份至 `f1a2b3c4d5e6` 再 `rollback` 通过 readiness 验收，以及 6 容器旧镜像 Browser 接管与停启切换新镜像/`snapshot.json` 演练依赖实施方在修复重建 `api` 镜像后重跑 `.scratch/verify_ac007.py` 与 `.scratch/verify_ac007_adoption.py` 的结果（`progress.md`）；测试审阅侧已独立核对两份演练脚本断言覆盖与迁移备份恢复单测。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS
