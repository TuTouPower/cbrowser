# Task review t103（reviewer_focus: 代码）

- task：`t103_profile_advanced_options_cleanup`
- spec：`docs/tasks/t103_profile_advanced_options_cleanup/task.md`
- diff_anchor：`2d93270b2ae45922fcba865a49e9a183d61e89db`
- target：`git diff 2d93270b2ae45922fcba865a49e9a183d61e89db`
- round：1
- reviewed_at：2026-11-22T16:03:13+08:00

reviewed_scope: 939f20f613a5c96d

## Findings

### t103_code_f001 - SQLite 迁移连接未配置 `isolation_level=None` 与显式 `BEGIN`，中途失败回滚后泄漏 `_alembic_tmp_profiles` 并阻断重试

- 严重度：important
- 锚点：违反 `AC-004`（「注入 DDL/DML 中途故障时 schema、行、快照与 `alembic_version` stamp 一并回退；迁移后……再跑 `upgrade head`」）
- 位置：`src/backend/migrations/env.py:38-86`（联动 `src/backend/migrations/versions/0016_retire_profile_options_and_launch_args.py:27-53`）
- 问题：本任务在 `do_run_migrations` 为 Alembic 配置了 `transactional_ddl=True` 与 `transaction_per_migration=True`（`src/backend/migrations/env.py:42-43`），但 `run_migrations_online`（`engine_from_config`，第 78-85 行）与 `run_async_migrations`（`async_engine_from_config`，第 54-61 行）创建的 SQLite 引擎未在 `connect` 事件将 `dbapi_connection.isolation_level` 设为 `None` 并在 `begin` 事件显式执行 `BEGIN`。在 Python 标准库 `sqlite3` 默认 `isolation_level=""` 下，仅 DML 会隐式开启事务，而 `0016` 调用 `op.batch_alter_table("profiles", recreate="always")` 最先执行的 `CREATE TABLE _alembic_tmp_profiles (...)` 属于 DDL，因此未入事务即直接落盘提交；直到随后的 `INSERT INTO _alembic_tmp_profiles` 才开启隐式事务。实测从 `f1a2b3c4d5e6` 升级并在 `_drop_retired_profile_columns` 之后（`apply_launch_args_profile_updates`）注入故障，回滚后 `sqlite_master` 仍残留 `_alembic_tmp_profiles` 表，导致修复故障后重跑 `run_database_migrations` / `command.upgrade(cfg, "head")` 直接抛出 `sqlite3.OperationalError: table _alembic_tmp_profiles already exists`。
- 建议：在 `src/backend/migrations/env.py` 为同步及异步 SQLite 引擎（`connectable` / `connectable.sync_engine`）注册 `connect`（置 `dbapi_connection.isolation_level = None`）与 `begin`（执行 `conn.exec_driver_sql("BEGIN")`）事件监听（注意迁移连接不可开启 `PRAGMA foreign_keys=ON`，以免 `batch_alter_table` 执行 `DROP TABLE profiles` 时触发外键 `ON DELETE CASCADE`），并在单测中断言回滚后 `sqlite_master` 零残留 `_alembic_tmp_*` 表且可成功重跑 `upgrade head`。

### t103_code_f002 - `locale=None` 且 `geoip=True` 时仅含可映射 `--accept-lang` 被静默丢弃且未设定 `resolved_locale`

- 严重度：important
- 锚点：违反 `AC-002`（「语言夹具覆盖显式 `locale`、`locale=null` 配合 `geoip` 开关、多值 `--accept-lang`、重复项……与超枚举项……均先确定等价映射或经用户裁决后再移除」）与行为缺陷（静默丢失语言配置）
- 位置：`src/backend/cbrowser/adapters/database/launch_args_migration.py:334-357`
- 问题：在 `locale is None`、`geoip_enabled=True` 且无 `--lang` 仅含 `--accept-lang` 时，`classify_launch_args_entry` 第 337 行对末项计算 `eq_locale = _equivalent_accept_locale(val)`：若结果为 `None`（例如 `--accept-lang=ja-JP,ja` 或 `--accept-lang=en-US,zh-CN`），第 338-348 行将其标为 `需裁决` 并阻断迁移；但若 `_equivalent_accept_locale(val)` 返回 `"en-US"` 或 `"zh-CN"`（如 `--accept-lang=zh-CN,zh`），第 350-357 行却走 `else` 分支以 `action="drop_overridden_by_geoip_or_earlier"` / `reason="shadowed_by_geoip_or_later_accept_lang"` 直接丢弃，既未赋值 `resolved_locale = eq_locale`（与 `geoip=False` 第 410-438 行提升至 `resolved_locale` 不一致），也未因同时启用 `geoip` 存在二义性而阻断。对照 `cloakbrowser/browser.py` 的 `maybe_resolve_geoip`（仅读取 `--lang` / `--fingerprint-locale` 而不读 `--accept-lang`）与 `build_args`（仅覆盖 `--lang` / `--fingerprint-locale` 而保留 `--accept-lang`），`geoip=True` 并未覆盖 `--accept-lang`；该分支在阻塞不可映射项的同时却静默丢弃可映射 `--accept-lang`，存在行为丢配与自相矛盾。
- 建议：统一该分支语义——若确认单语言 `--accept-lang` 等价于显式语言配置，应在无冲突时设置 `resolved_locale = eq_locale`；若认定 `locale=None` 配合 `geoip=True` 时显式 `--accept-lang` 与 IP 推断存在冲突需裁决，则应将该情形统一标为 `需裁决` 阻断迁移，避免静默丢弃。

### t103_code_f003 - `geoip=False` 下 `--lang` 与 `--accept-lang` 冲突阻断未在 `dispositions` 体现 `需裁决`

- 严重度：minor
- 锚点：行为缺陷 / `AC-002` 只读盘点处置分类一致性
- 位置：`src/backend/cbrowser/adapters/database/launch_args_migration.py:374-441`
- 问题：当 `locale is None`、`geoip_enabled=False` 且末项 `--lang` 与末项 `--accept-lang` 等价目标冲突（如 `--lang=zh-CN` 与 `--accept-lang=en-US`）时，第 374-420 行先将两者都记录为 `category="等价映射"`，第 433-436 行才往 `blocking` 追加冲突错误。虽然迁移会被 `blocking_errors` 阻断，但 `inventory` 中的 `dispositions` 没有任何条目标为 `需裁决`，与只读盘点“为每条参数记录等价映射或需裁决”的表述存在局部不一致。
- 建议：在检测到 `lang_candidate != accept_candidate` 时，将对应冲突条目在 `dispositions` 中的 `category` 更新为 `"需裁决"`、`action` 更新为 `"block_migration"`。

### t103_code_f004 - 新建函数 `classify_launch_args_entry` 圈复杂度过高（`CC ~= 51`）

- 严重度：minor
- 锚点：圈复杂度标准（新建函数 `CC >= 15` 记 `minor`）
- 位置：`src/backend/cbrowser/adapters/database/launch_args_migration.py:176-442`
- 问题：`classify_launch_args_entry` 将参数解析校验、`--mute-audio` / 冗余分类以及 `explicit locale` / `geoip=True` / `geoip=False` 三套语言决策全部耦合在 267 行单函数内，近似 McCabe 圈复杂度约 51（超过 `>= 15` 阈值），增加了分支漏处理与理解成本。
- 建议：拆分为基础标志扫描与三个独立语言决策 helper（显式 `locale`、`geoip=True`、`geoip=False`）。

### t103_code_f005 - `rewrite_profile_snapshots_for_launch_args` 含未使用参数 `inventory` 且 `audit_launch_args_database` 重复解析参数

- 严重度：minor
- 锚点：代码质量（死参数与重复逻辑）
- 位置：`src/backend/cbrowser/adapters/database/launch_args_migration.py:494-500,546-553,615-630`
- 问题：`rewrite_profile_snapshots_for_launch_args(conn, inventory)` 接收 `inventory` 参数但函数体完全未使用，而是重新全表查询并调用 `transform_migrated_config_dict`；此外 `audit_launch_args_database` 在调用 `classify_launch_args_entry` 后又重复调用 `_parse_args_value` 以填充 `raw_launch_args`。
- 建议：移除未使用的 `inventory` 参数（或直接消费其预计算结果），并由 `classify_launch_args_entry` 或中间结构一次返回已清洗的参数列表。

## 结论

- 本轮新发现：5 条（critical 0，important 2，minor 3）
- 未进表的提示：
    - 文件过大（依规不进 finding 表）：`src/backend/cbrowser/adapters/database/launch_args_migration.py`（646 行，新建即 ≥ 400 行 minor 阈值，建议后续按分类规则与 SQL 执行器拆分）；其余修改的非测试源码文件与测试文件均较基准净减行，生成产物 `schemas/openapi/cbrowser_v1.json`、`schemas/openapi/cbrowser_internal.json`、`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 与 `profile_field_classification.ts` 依规排除。
    - 圈复杂度 ≥ 10 提示（不进 finding 表）：`src/backend/cbrowser/adapters/database/launch_args_migration.py:143` `_parse_args_value`（`CC ~= 10`）、`src/backend/cbrowser/adapters/database/launch_args_migration.py:615` `rewrite_profile_snapshots_for_launch_args`（`CC ~= 10`）；既有高复杂度函数（`repository.py`、`runner.py`）本 task 未净增分支。
    - 7 视角扫描确认：已全面复核安全（`extra="forbid"` 与输入边界校验，无敏感信息入日志/硬编码）、契约一致性（`cbrowser_v1.json` / `cbrowser_internal.json` / `cbrowser_v1.d.ts` / `profile_field_classification.ts` / `export_*_protocol.py` / `generate_requirements.sh --check` / `AUTOGEN_DIFFS: []` 全对齐）、前端构建与样式门禁（`design:lint` / `design:check` / `npm test` 88 files 747 tests / `npm run build` 全通过）、性能与健壮性；另外 `src/backend/cbrowser/adapters/database/models.py:183-188` 与 `276-280` 存在历史重复 `__table_args__` 赋值（前序残留，非本 diff 引入）。
- 总体判断：六个无效字段移除、显式 `mute_audio` 与契约/UI 收口整体严谨，但存在 SQLite 迁移 DDL 事务未真正开启导致回滚泄漏 `_alembic_tmp_profiles` 以及 `geoip=True` 单 `--accept-lang` 静默丢配两项阻断缺陷，须修复后再重审。
- 系统性 follow-up：无（已只读运行 `task.py list` 核对，扩展治理已由 `t104` 承接，本轮问题均属 `t103` 本身范围）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已核对 `models.py`/`domain/models.py`/`repository.py`/`router.py`/`probe_collector.py`/`runner.py`/`ProfileForm.tsx`/`i18n.tsx`/`types.ts` 及全仓 grep 确认 6 字段彻底移除，且重跑 OpenAPI/TS 生成比对、`export_*_protocol.py --check`、`test_t103_retire_options_and_runner.py`、`test_t103_profile_cleanup_api.py` 与前端 `npm test`/`build`/`design:check` 均通过。
- AC-002：TICK-VOID，re_verified。核查 `src/backend/cbrowser/adapters/database/launch_args_migration.py:334-357` 发现 `locale=None` 且 `geoip=True` 时对有效单语 `--accept-lang` 仅记录覆盖丢弃而不设 `resolved_locale`、却对超枚举值阻断，存在等价映射缺失与语义矛盾（`t103_code_f002`）。
- AC-004：TICK-VOID，re_verified。独立复测 `src/backend/migrations/env.py` + `0016` 在 `apply_launch_args_profile_updates` 注入故障后，回滚残留 `_alembic_tmp_profiles` 导致后续 `run_database_migrations` 报 `table _alembic_tmp_profiles already exists` 崩溃，未满足 schema 完整回退及后续重跑 `upgrade head`（`t103_code_f001`）。
- AC-005：TICK-VALID，trust_prior。[deploy] 已核对 `runner.py:667-701` 与 `i18n.tsx:359,399` 代码路径及文案与 AC 一致，真实固定引擎语言/音频/2×2 会话恢复矩阵依赖实施侧 `.scratch/verify_ac005_inner.py` 与 `progress.md` 记录证据。
- AC-007：TICK-VALID，trust_prior。[deploy] 已核对 `docker_adapter.py:2399-2425`、`supervisor/control_server.py:218-243`、`0016` 与 `docs/specs/release_deployment.md` 升级接管及先 `restore` 后 `rollback` 约束实现，隔离真实部署与 6 容器接管演练依赖 `.scratch/verify_ac007.py`、`.scratch/verify_ac007_adoption.py` 与 `progress.md` 记录证据。

coverage = 3 / 5
建议合并前人工抽查 trust_prior 项

verdict: FAIL

## Round 2 (2026-11-22T19:02:53+08:00)

- round：2
- reviewed_at：2026-11-22T19:02:53+08:00

reviewed_scope: 3eaff827b9e80146

## Findings

本轮零新发现。

## 结论

- 前轮 finding 复核：
    - `t103_code_f001`：已消除。核查 `src/backend/migrations/env.py:38-108` 新增 `_configure_sqlite_transactional_ddl`，已为 `run_async_migrations`（`connectable.sync_engine`）与 `run_migrations_online`（`connectable`）统一注册 `connect`（`dbapi_connection.isolation_level = None`）与 `begin`（`conn.exec_driver_sql("BEGIN")`）；独立执行同步 `sqlite:///` 与异步 `sqlite+aiosqlite:///` 在 `0016` `apply_launch_args_profile_updates` 处注入异常的回滚测试，确认 `sqlite_master` 零残留 `_alembic_tmp_*` 表、`alembic_version` 回退至 `f1a2b3c4d5e6`，且解除故障后重跑 `run_database_migrations` / `command.upgrade(cfg, "head")` 均顺利升至 `a10300160001`。
    - `t103_code_f002`：已消除。核查 `src/backend/cbrowser/adapters/database/launch_args_migration.py:416-465`（`_resolve_with_geoip`），当 `locale is None` 且 `geoip_enabled=True` 且无 `--lang` 时复用 `_resolve_accept_lang_series` 将可映射单语言 `--accept-lang` 提升为 `resolved_locale`，超枚举/多语言阻断为 `需裁决`；当同时存在 `--lang` 与 `--accept-lang` 时亦对 `--accept-lang` 一致校验并在冲突时阻断，不再静默丢配。
    - `t103_code_f003`：已消除。核查 `src/backend/cbrowser/adapters/database/launch_args_migration.py:357-378,455-461,481-487`，冲突路径调用 `_relabel_conflict_dispositions` 将活跃促进条目在 `dispositions` 中的分类与动作统一改标为 `需裁决` / `block_migration`。
    - `t103_code_f004`：已消除。`classify_launch_args_entry` 已拆分为 `_scan_raw_launch_args`、`_resolve_with_explicit_locale`、`_resolve_accept_lang_series`、`_resolve_lang_last_wins`、`_resolve_geoip_out_of_enum_lang`、`_resolve_with_geoip`、`_resolve_without_geoip` 等单一职责 helper，实测全文件函数近似 McCabe 圈复杂度均已降至 `<= 10`。
    - `t103_code_f005`：已消除。`audit_launch_args_database` 改为调用 `_classify_launch_args_with_parsed` 消除重复 `_parse_args_value` 解析；`rewrite_profile_snapshots_for_launch_args(conn)`（`launch_args_migration.py:744` 与 `0016_retire_profile_options_and_launch_args.py:52`）已移除未使用参数 `inventory` 且全仓仅有一处生产调用与单测引用。
- 本轮新发现：0 条
- 未进表的提示：
    - 文件过大（依规不进 finding 表）：`src/backend/cbrowser/adapters/database/launch_args_migration.py`（773 行，新建 ≥ 400 行 minor 阈值、仍低于 800 行 important 阈值，本轮拆解 helper 后各函数边界清晰）。
    - 圈复杂度 ≥ 10 提示（不进 finding 表）：`src/backend/cbrowser/adapters/database/launch_args_migration.py:143` `_parse_args_value`、`184` `_scan_raw_launch_args`、`496` `_classify_launch_args_with_parsed` 与 `744` `rewrite_profile_snapshots_for_launch_args` 均约 `CC ~= 10`（未达 15）。
    - 7 视角复扫确认：本轮修复未触及契约/前端/安全边界，已复跑 `test_t103_launch_args_migration.py`、`test_t103_retire_options_and_runner.py`、`test_t103_profile_cleanup_api.py`、`test_t056_migrations.py`、`test_t089_wrapped_snapshot_migration.py`、`test_t058_profile_field_classification.py`、`test_repo_hygiene.py`、`test_t051_generation_hygiene.py`（64 passed），以及 `sqlite:///` 与 `sqlite+aiosqlite:///` 中途故障回滚及重试验证通过。
- 总体判断：Round 1 全部 5 条 finding（含 2 条阻断项）均已从根因彻底修复且未引入新缺陷，代码质量与契约/迁移实现满足 AC 要求。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已复核后端模型/DTO/API/Runner/探针与前端表单/i18n/OpenAPI 生成产物移除 6 个无效字段，且 `test_t103_retire_options_and_runner.py`、`test_t103_profile_cleanup_api.py` 与 `test_t058_profile_field_classification.py` 复跑全部通过。
- AC-002：TICK-VALID，re_verified。已核对 `launch_args_migration.py` 拆分后的盘点与语言优先级实现（含 `locale=None, geoip=True` 单 `--accept-lang` 提升与冲突改标 `需裁决`）及 `POST/PATCH/PUT` 传 `launch_args` 返回 422 零写入，`test_t103_launch_args_migration.py` 与 `test_t103_profile_cleanup_api.py` 复跑全部通过。
- AC-004：TICK-VALID，re_verified。已核查 `src/backend/migrations/env.py` 为同步/异步 SQLite 注册 `isolation_level=None` 与显式 `BEGIN`，并独立复测 `sqlite:///` 与 `sqlite+aiosqlite:///` 在 `0016` 中途故障回滚后 `sqlite_master` 零残留 `_alembic_tmp_*` 且重跑 `upgrade head` 成功，`test_t103_launch_args_migration.py` 与 `test_t103_profile_cleanup_api.py` 复跑全部通过。
- AC-005：TICK-VALID，trust_prior。[deploy] 已核对 `runner.py:667-701` 与 `i18n.tsx:359,399` 代码路径及边界文案，固定 146 引擎的 Web 语言、PulseAudio 440Hz 静音对照与 2×2 `restore_session` 四格真机表现依赖 `progress.md` 记录的 `.scratch/verify_ac005_inner.py` 重跑实测证据。
- AC-007：TICK-VALID，trust_prior。[deploy] 已核对 `docker_adapter.py:2399-2425`、`supervisor/control_server.py:218-243`、`0016` 与 `docs/specs/release_deployment.md` 升级接管及先 `restore` 后 `rollback` 约束实现，隔离 `scripts/deploy.sh` 升/回退与 6 容器接管演练依赖 `progress.md` 记录的 `.scratch/verify_ac007.py` 与 `.scratch/verify_ac007_adoption.py` 重建镜像重跑证据。

coverage = 3 / 5
建议合并前人工抽查 trust_prior 项

verdict: PASS
