---
tid: "t103"
slug: "profile_advanced_options_cleanup"
title: "清理 Profile 无效高级选项与退役通用 launch_args 并对齐扩展及迁移契约"
status: "done"
branch: "t103_profile_advanced_options_cleanup"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "2d93270b2ae45922fcba865a49e9a183d61e89db"
spec_source_sha: "2d93270b2ae45922fcba865a49e9a183d61e89db"
depends_on: ""
conflicts_with: ""
note: "来源 p166（2026-11-22 Codex 评估清理决策）"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- **验证策略确认**：`docs/blueprint/testing.md` 已设置 `verification_policy=project_configured`；本 task 适用契约测试、后端单元/集成测试、OpenAPI/字段分类/前端类型生成一致性、前端 Vitest/设计门禁与构建（经 `scripts/run_gates.sh` 统一入口），以及 `[deploy]` AC-005（固定 arm64 `146.0.7680.177.3` 有头容器 Web 语言主备、`mute_audio` 音源正负对照、`restore_session` 2×2 四格对照）与 AC-007（OrbStack 隔离 release 升级、在跑实例接管及停写→恢复旧库→按旧 release 启动回退演练）；公网可达性与原生 Linux x86_64 沿用 `testing.md` 用户豁免口径不跑。

- **前置 Spike（2026-11-22）**：只读检查线上 `cbrowser-db`（`f1a2b3c4d5e6`，5 Profile / 6 包装版本）、`config/deploy/backups/*.db` 与 `data/v2/cbrowser.db`，`launch_args` 均为 `[]`；扫描仓内 `scripts/`/`docs/`/`src/`/`tests/` 无外部原始 `launch_args` 消费方；获用户明确裁决——彻底退役 `launch_args`、保留显式 `mute_audio`（默认关）、`AutomationControlled` 视为 `冗余` 归并、语言仅由单语 `locale` 收口。

- **实现与测试收口（2026-11-22）**：

    - 后端域模型/API/数据库与 Alembic `0016`（`a10300160001`，开启 `env.py` `transactional_ddl=True` 与 `transaction_per_migration=True`）：删除 6 个无效选项与 `launch_args`（含删除 `cbrowser/launch_args.py`），新增 `mute_audio: bool = False`，通过 `extra="forbid"` 在 `POST/PATCH/PUT` 边界 422 零写入拒绝，存量通过 `launch_args_migration.py` 逐条归并并阻塞未映射参数（仅迁移 `--mute-audio`、`--accept-lang=` 等已登记规则与 `AutomationControlled` 冗余折叠）。
    - 前端表单、i18n 与代码生成：`ProfileForm.tsx` 移除 7 个退役控件与预设列表、新增“静音启动 / Mute audio”开关，更新 `formRestoreSessionHelp` 中英文边界说明；重导 OpenAPI、`profile_field_classification.ts` 与 `cbrowser_v1.d.ts`。
    - 废弃/替代旧测试明细（遵循 `AGENTS.md` TDD 原则）：整文件删除已退役模块的 `tests/unit/test_launch_args.py`（其中仍在役的 `test_runtime_storage_defaults_target_uid_1000` 迁入 `tests/unit/test_domain_and_repository.py`）与 `tests/integration/test_profile_launch_args_api.py`（由 `tests/integration/test_t103_profile_cleanup_api.py` 与 `tests/unit/test_t103_launch_args_migration.py`、`tests/unit/test_t103_retire_options_and_runner.py` 替代覆盖）；其余单测/集成/E2E 与 21 个前端测试文件中的旧字段夹具及断言已按新语义替换并在注释说明来源 `t103`。
    - 容器镜像重编：`scripts/build_images.sh` 重建 6 镜像（`api=sha256:4b5f6a1e...`、`gateway=sha256:3d0e51cb...`、`supervisor=sha256:95ea169a...`、`browser=sha256:0ab2bfe3...`、`stream=sha256:c43bffb8...`、`caddy=sha256:76c6b066...`），`scripts/verify_image_packages.py` 验证 5 个 Python 镜像全部与 `uv.lock` 一致（`43/19/22/40/35`）。

- **Round 1 修复与全量重验（2026-11-22）**：按 `review_code.md` / `review_test.md` 全部 10 条 finding 修复并重建 `api` 镜像（`sha256:f45501e2...`）：`migrations/env.py` 增加 SQLite `connect`（`isolation_level=None`）与 `begin`（`BEGIN`）事件保证 DDL+DML 原子回退零残留 `_alembic_tmp_*`；`launch_args_migration.py` 拆分语言决策 helper（各函数 `CC <= 10`）、补全 `locale=None, geoip=True` 单 `--accept-lang` 提升与冲突标 `需裁决`、去重解析并移除 `rewrite_profile_snapshots_for_launch_args` 死参数；`test_t103_profile_cleanup_api.py` 与 `test_t103_launch_args_migration.py` / `test_t103_retire_options_and_runner.py` 补全真实 `SupervisorCore` + `RuntimeCoordinator` 协调、`Clone-v2` 与含状态克隆（运行中 409 / 停机复制）、在役默认值与 `sqlite+aiosqlite` 故障回退测试，并重跑全部门禁、镜像包校验及 `[deploy]` AC-005 / AC-007 / 3 项 E2E。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-22T16:03:13+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t103_code_f001|important|已修|为 sync/async SQLite 迁移引擎注册 isolation_level=None 与显式 BEGIN，回滚零残留 \_alembic_tmp_profiles 且重跑 upgrade head 成功|src/backend/migrations/env.py:38-107, tests/unit/test_t103_launch_args_migration.py:463-605|
|t103_code_f002|important|已修|locale=None 且 geoip=True 仅含 --accept-lang 时复用 \_resolve_accept_lang_series 将可映射单语提升至 resolved_locale，超枚举/多语标需裁决|src/backend/cbrowser/adapters/database/launch_args_migration.py:416-430|
|t103_code_f003|minor|已修|检测到 --lang 与 --accept-lang 冲突时将活跃条目 disposition 改标为 需裁决/block_migration|src/backend/cbrowser/adapters/database/launch_args_migration.py:357-378,448-490|
|t103_code_f004|minor|已修|将 classify_launch_args_entry 拆分为 8 个职责单一 helper，每函数 McCabe CC 均 \<= 10|src/backend/cbrowser/adapters/database/launch_args_migration.py:176-570|
|t103_code_f005|minor|已修|提取 \_classify_launch_args_with_parsed 消除重复解析，并移除 rewrite_profile_snapshots_for_launch_args 死参数 inventory|src/backend/cbrowser/adapters/database/launch_args_migration.py:496-699,744, 0016:52|
|t103_test_f001|important|已修|移除 start_profile 替身，改用真实 SupervisorCore + create_control_app + FakeDockerAdapter 验证 N=1 与 N+1=2 snapshot.json 落盘|tests/integration/test_t103_profile_cleanup_api.py:351-565|
|t103_test_f002|important|已修|接入真实 RuntimeCoordinator + ProfileService + 拦截传输，断言 bound=1 < current=2 时协调器主动发送 config_version=2|tests/integration/test_t103_profile_cleanup_api.py:424-565|
|t103_test_f003|important|已修|补全仅配置克隆 Clone-v2 运行态断言、运行中含状态克隆 409 拒绝及停机解绑后含状态克隆用户数据与版本一致性断言|tests/integration/test_t103_profile_cleanup_api.py:310-496|
|t103_test_f004|minor|已修|在单测与 API 创建默认响应中补全 clipboard_sync/set_google_default/restore_session/capture_preview/geoip/locale/timezone 等全部在役默认值断言|tests/unit/test_t103_retire_options_and_runner.py:53-70, tests/integration/test_t103_profile_cleanup_api.py:88-100|
|t103_test_f005|minor|已修|直接断言 audit_launch_args_database 返回 需裁决 分类，并补全 wrapped=False 平铺阻断/损坏快照与语言冲突矩阵用例|tests/unit/test_t103_launch_args_migration.py:299-460|

### Round 2 (2026-11-22T19:04:36+08:00)

Round 2 零 finding（Code Reviewer 与 Test Reviewer 均验证 Round 1 全部 10 条 finding 已消除且无新增缺陷）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`bash scripts/run_gates.sh` 全项通过（`protocol_drift_check`、`generate_requirements.sh --check`、契约 `388 passed, 1 skipped` [389 cases]、后端 unit `2423 passed, 13 skipped` + serial `85 passed` [2521 cases]、后端 integration `219 passed, 18 skipped` + serial `4 passed` [241 cases]、前端 Vitest `88 passed (88)` / `747 passed`、`design:lint` `0 error / 0 warning`、`design:check`、`check:api`、`vite build`、`verify:selkies`）；镜像包校验 `scripts/verify_image_packages.py` 通过（`api=43, gateway=19, supervisor=22, browser=40, stream=35` 与 `uv.lock` 一致）；定向真实容器 E2E 通过（`test_native_build_contexts_e2e.py`、`test_frontend_adapter_build.py`、`test_runtime_profile_defaults_e2e.py`、`test_t068_fingerprint_gate_e2e.py` 合计 `16 passed`；修复后重跑 `test_frontend_app_e2e.py::test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state`、`test_browser_runtime_e2e.py::test_ac001_persistence_and_dual_profile_isolation` 与 `test_supervisor_upgrade_recovery_e2e.py::test_upgrade_of_running_profile_self_heals` 合计 `3 passed in 103.59s`）。
- 黑盒：`[deploy] AC-005`（`.scratch/prepare_migrated_muted_snap.py` + `.scratch/verify_ac005_inner.py` 于修复后 `api` / `browser` 镜像内实测固定 arm64 `146.0.7680.177.3`）：语言 `en-US` → HTTP `Accept-Language: en-US,en;q=0.9`、`navigator.languages=["en-US"]`，`zh-CN` → `zh-CN,zh;q=0.9`、`["zh-CN"]`，且 `zh-CN` 会话下内置页 `chrome://settings` 保持英文 `"Settings"`、`chrome://version` 显示 `"Chromium 146.0.7680.177"`；音频 440Hz Web Audio 在 `cbrowser_sink.monitor` 实采，迁移 `mute_audio=True` 为全零静音（`samples=66560, max_abs=0, non_zero=0`）、默认 `mute_audio=False` 有声（`samples=81920, max_abs=19661, non_zero=79832`）；`restore_session`（开/关）× `Preferences.session.restore_on_startup`（1/5）四格对照仅 `(False, 5)` 不恢复（`["about:blank"]`），其余三格均恢复双标记页签。`[deploy] AC-007`（修复后重建 `api` 镜像重跑全通过）：Part 1（`.scratch/verify_ac007.py` 对独立实例 `cbt103` HTTPS `56671` 执行真实 `scripts/deploy.sh` 升级 `20261122185400-2d93270` → `20261122185418-2d93270`、升级前备份 `cbrowser-20261122185421.db`、迁移至 `a10300160001`、未经 `restore` 回退被明确拒绝、`deploy.sh restore` 恢复旧库并回退旧 release 至 `f1a2b3c4d5e6` 且旧 Profile `a3b7b86f-2ed9-4cb1-bbd3-512ea8a20d07` 可查，注：因宿主线上 `0084..0088` 占用 UDP `30000..30004` 且 `compose.yaml` 未开放 UDP 端口起点覆盖，`deploy.sh` 演练与在线实例互斥避免误停用户环境）；Part 2（`.scratch/verify_ac007_adoption.py` 在隔离 UDP `34000+` 6 容器拓扑运行旧镜像 Browser `195e98494071` 时先升级 API/Gateway/Supervisor 至 `t103`，验证在跑 Browser 不被替换并沿用 `inst_fc3fcc6af88f` 与绑定版本 `1`，在线修改后当前版本升至 `2`，停机重拉后切换新镜像 `0ab2bfe363e2` 容器 `dca64b988906` 且容器内 `/run/cbrowser/runtime/snapshot.json` 与 `/data/runtime/{pid}/snapshot.json` 一致含 `version=2, screen_width=1600, mute_audio=true` 且无 7 个已退役字段）。
- review：full 级 Round 2 `overall=PASS`（`review_code.md` 与 `review_test.md` 均 `verdict: PASS`、`reviewed_scope: 3eaff827b9e80146`、`ac_review=ok`、`coverage = 3 / 5`，Round 1 全部 10 条 finding 均已消除，Round 2 零新增 finding；两项 `[deploy]` AC 按规则记 `trust_prior` 建议合并前抽查）

### 结果摘要

- 彻底清理 `humanize`、`human_preset`、`auto_launch`、`allow_3p_cookies`、`transparent_proxy`、`portable_cookies` 与通用 `launch_args`，新增显式 `mute_audio: bool = False`，保持 `extension_paths` 契约不动交由 `t104`（`p165`）承接。
- 通过 Alembic 0016 事务性 DDL+DML 确定性迁移存量历史配置并阻断未注册/冲突残留，配合 API `extra="forbid"`、OpenAPI/TS 自动生成与前后端/真实引擎黑盒验证闭环。

### 长期文档闭环

- 已于 [`docs/specs/profile_management.md`](../../specs/profile_management.md) 与 [`docs/specs/release_deployment.md`](../../specs/release_deployment.md) front matter `tasks` 登记 `t103`，并同步更新 `docs/blueprint/architecture.md`、`docs/blueprint/security.md`、`docs/blueprint/domain.md`、`docs/blueprint/browser_runtime.md`、`docs/blueprint/persistence.md` 与 `docs/blueprint/testing.md`；`profile_management` 的扩展改造由后续 `t104`（`p165`）承接。
