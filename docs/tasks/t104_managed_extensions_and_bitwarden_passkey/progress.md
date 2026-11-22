---
tid: "t104"
slug: "managed_extensions_and_bitwarden_passkey"
title: "实现受控多扩展资产管理、显式扩展权限及容器内 Bitwarden Passkey 支持"
status: "done"
branch: "t104_managed_extensions_and_bitwarden_passkey"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "41a4a3e848e673007090e4489beb0fbdb7ee5765"
spec_source_sha: "41a4a3e848e673007090e4489beb0fbdb7ee5765"
depends_on: "t103"
conflicts_with: ""
note: "来源 p165 与 p166（承接 t103 移出的 AC-003/AC-006、受管扩展库与 Bitwarden Passkey 支持）"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 先行完成正式 spike `docs/spikes/s029_extensions_and_bitwarden_passkey/report.md` 与长期事实 `docs/findings/d055_extensions_and_bitwarden_passkey.md`，实证裁决：固定 `146.0.7680.177.3` 自由模式仅支持开发者模式 `Load unpacked`（经 GTK3 对话框选择持久目录）；CRX3 需按 `SignedHeaderData.crx_id` 匹配签发公钥回写 `manifest.json["key"]` 保持 ID/存储连续；`cloakbrowser 0.6.4` 硬编码 `IGNORE_DEFAULT_ARGS` 须由 `cbrowser/runtime_agent/stealth_launch.py` 在 `allow_extensions=True` 时显式撤除 `--disable-extensions` 与 `--disable-component-extensions-with-background-pages`。
- 实机重启持久性真机排障（`[deploy]` AC-004）发现：`Supervisor/DockerAdapter.cleanup_container_by_name` 原实现直接调用 `c.remove(force=True)`（SIGKILL），导致 Chromium `Preferences` 与本地扩展示图在停机时来不及落盘。已从根因修正：删除运行中的 `browser` 容器前先优雅执行 `stop(timeout=8)` 触发 `BrowserRunner.stop()` -> `context.close()` 落盘后移除容器，并补单测与真机跨重启实证。
- 镜像与依赖闭包同步更新 `config/docker/browser_runtime/Dockerfile(.dockerignore)` 与 `config/docker/supervisor_runtime/Dockerfile(.dockerignore)` 引入 `cbrowser/extensions`，通过 `scripts/build_images.sh` 重建全部 6 个镜像并由 `scripts/verify_image_packages.py` 复验（api 43 / gateway 19 / supervisor 22 / browser 40 / stream 35 包零漂移）。
- 在独立防冲突隔离前缀与端口拓扑上执行真实重建六镜像端到端验收（`.scratch/t104_deploy_verify/verify_ac004.py`、`verify_ac005.py`、`verify_migration_and_restore.py`）：完整实证 Caddy/UI 冒烟、默认关态、`[ext1, ext2]` 并发与自由扩展拒载、Free 模式 GTK3 Load unpacked 跨重启持久、切回关态完全停用、双受管 Profile 同扩展 `chrome.storage.local` 交叉隔离（`isolated-secret-A` / `isolated-secret-B` 互不串用）与 Stream 零挂载隔离、`0016 -> 0017` ID/存储连续性与 `restore_point.py` 备份恢复，以及官方 Bitwarden CRX3（`2026.11.0`，`nngceckbapebfimnlniiiahkandclblb`）经认证代理同步 `ghcr.io/dani-garcia/vaultwarden:alpine`、Policy Agent 策略零直连阻断与 WebAuthn `navigator.credentials.create/get` 同 ID Passkey 闭环；清理后无残留容器/网络/卷。
- Round 1 full review 修复完成后重新跑通 `scripts/run_gates.sh`（contract 388 passed / 1 skipped、unit 2444+85 passed / 13 skipped、integration 225+4 passed / 18 skipped、frontend 88 files / 752 passed、`design:lint` 0 error / 0 warning、`design:check` clean、Vite + Selkies 构建校验通过），并增量重建 `.scratch/t104_images.json` 全部 6 个镜像重新通过 `verify_image_packages.py` 与真实容器 `verify_ac004.py`、`verify_ac005.py`、`verify_migration_and_restore.py` 复验。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-23T01:53:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t104_code_f001|important|已修|`ProfileService.update_profile` 对仅传 `allow_extensions=True` 或平台/字体切换但 Profile 不存在均先加载并校验 `current is None` 抛 `ProfileNotFoundError`（404），补充 API 回归测试|`src/backend/cbrowser/services/profile_service.py:766-820`, `tests/integration/test_t104_extensions_api.py:309-332`|
|t104_code_f002|important|已修|`unpack_safe_zip_entries` 改由 `_read_bounded_zip_entry` 对 `zf.open` 按剩余解压预算分块流式读取并统计真实字节数，伪造小 `file_size` 无法触发 unbounded 解压，补充测试|`src/backend/cbrowser/extensions/manifest.py:234-308`, `tests/unit/test_t104_extensions_manifest.py:206-258`|
|t104_code_f003|important|已修|`ExtensionCatalogService` 按 `(root, asset_id)` 持有共享异步锁串行化导入与删除磁盘/写库临界区；`ProfileRepository.create_profile/update_profile` 同一 `write_transaction` 内通过 `_assert_verified_extensions_in_tx` 复核引用并转译 422，补充并发测试|`src/backend/cbrowser/services/extension_catalog.py:27-196`, `src/backend/cbrowser/adapters/database/repository.py:61-88`, `tests/integration/test_t104_extensions_api.py:335-404`|
|t104_code_f004|important|已修|`ExtensionLibrarySection` 移除 `#{entry.display_number}` 展示，仅渲染 `{entry.profile_name}` 并更新单测断言不含 `#4`|`src/frontend/src/features/extensions/ExtensionLibrarySection.tsx:52-58`, `src/frontend/src/features/settings/SettingsPage.test.tsx:253-256`|
|t104_code_f005|minor|已修|`ExtensionAssetRepository._reference_map` 改用 `tuple_(profile_id, version).in_(bound_pairs)` 单次批量查快照消除 N+1|`src/backend/cbrowser/adapters/database/extension_repository.py:239-277`|
|t104_code_f006|minor|已修|清理 `ExtensionLibrarySection` 未消费 props `selectedIds` / `onUploaded` 及硬编码 `"Bound"` 分支|`src/frontend/src/features/extensions/ExtensionLibrarySection.tsx:66-210`|
|t104_code_f007|minor|已修|在 `useCreateProfileMutation`、`useUpdateProfileMutation`、`useDeleteProfileMutation`、`useDeletionBatchQuery` 与 `useDuplicateProfileMutation` 同步失效 `extensionKeys.all` 并补单测|`src/frontend/src/features/profiles/useProfilesQuery.ts:315-443`, `src/frontend/src/features/profiles/useProfilesQuery.test.tsx:1579-1635`|
|t104_code_f008|minor|已修|`manifest.py` 提供公开 `extract_directory_metadata`（仅读 `_locales` 与声明图标），`ExtensionCatalogService.adopt_existing` 将目录扫描与校验整体放入 `asyncio.to_thread`，消除私有符号跨模块导入|`src/backend/cbrowser/extensions/manifest.py:424-467`, `src/backend/cbrowser/services/extension_catalog.py:222-279`, `src/backend/cbrowser/adapters/database/extension_paths_migration.py:27-115`|
|t104_code_f009|minor|已修|`scripts/restore_point.py` 提取 `_backup_extensions_dir` 并过滤 `.` 开头临时目录（如 `.staging-*`）与非 64 位 hex 目录，补单测|`scripts/restore_point.py:252-279`, `tests/unit/test_t104_supervisor_and_runner.py:454-496`|
|t104_code_f010|minor|已修|运行 `md_format.py` 重新格式化 `d055` 与 `s029/report.md`，`md_format.py --check` 输出格式一致|`docs/findings/d055_extensions_and_bitwarden_passkey.md`, `docs/spikes/s029_extensions_and_bitwarden_passkey/report.md`|
|t104_code_f011|minor|已修|拆分 `manifest.py`、`extension_paths_migration.py`、`stealth_launch.py`、`supervisor/core.py`、`docker_adapter.py` 与 `scripts/restore_point.py` 新增/改写的高分支函数，新增 helper 均低于阈值且不增既有大函数分支|`src/backend/cbrowser/extensions/manifest.py`, `src/backend/cbrowser/adapters/database/extension_paths_migration.py`, `src/backend/cbrowser/runtime_agent/stealth_launch.py`, `src/backend/cbrowser/supervisor/core.py`, `src/backend/cbrowser/supervisor/docker_adapter.py`, `scripts/restore_point.py`|
|t104_test_f001|important|已修|`ambiguous_candidates` 改为复用同一 `same.der` 公钥构造 `2.0.0` / `3.0.0` 候选，新增同快照重复 `chromium_id` 歧义场景 `ambiguous_duplicate_cid_in_snapshot`，并在全部阻断场景精确断言 `p1`、版本与分类关键词|`tests/unit/test_t104_extension_paths_migration.py:390-519`|
|t104_test_f002|important|已修|移除 `# type: ignore[method-assign]` 与对 `core.report_terminal_observation` 的 `AsyncMock` 覆写，通过既有 `httpx.MockTransport` 捕获并断言真实的 `observed_state="error"` / `reason="extension_unavailable"` 上报载荷|`tests/unit/test_t104_supervisor_and_runner.py:237-293`|
|t104_test_f003|minor|已修|在 `ProfileForm.test.tsx` 补充 `mode="edit"` 回显、`ext-move-down-*`、`ext-remove-*`、关闭开关 hides 与增量 diff 提交断言；在 `profile_field_diff.test.ts` 补充 `allow_extensions` / `extension_ids` 分类与 `hasRuntimeConfigChange` 用例|`src/frontend/src/features/profiles/ProfileForm.test.tsx:1027-1102`, `src/frontend/src/features/profiles/profile_field_diff.test.ts:26-112`|
|t104_test_f004|minor|已修|清理 `test_verified_mapped_upgrade_preserves_order_id_continuity_and_snapshots` 无用 `if False` 死分支，补充迁移后包装与平铺快照 `ProfileConfig.model_validate`、非空库二次 `upgrade("head")` 幂等与 `profile_runtimes`/`user_data_dir` 保留断言|`tests/unit/test_t104_extension_paths_migration.py:262-382`|

### Round 2 (2026-11-23T02:35:01+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t104_code_f012|minor|遗留|Round 2 修补使 `profile_service.update_profile` / `repository.update_profile` / `extract_directory_metadata` 达 `CC >= 15`，与 `t104_code_f011` 残余项一并记入独立清理待办以保持本轮 PASS `reviewed_scope` 稳定|p167|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`scripts/run_gates.sh` 全部通过（`contract` `388 passed, 1 skipped`；`unit` `2444 passed, 13 skipped` + `85 passed`；`integration` `225 passed, 18 skipped` + `4 passed`；`frontend_test` `88 files / 752 passed`）；`design:lint`（0 error / 0 warning）、`design:check`、`check:api`、`test:types`、`Vite build`、`verify_frontend_dist` 及四份协议 `--check` 全通过。
- 黑盒：增量重建全部 6 个 Docker 镜像经 `verify_image_packages.py` 核验依赖闭合（`api` 43 / `gateway` 19 / `supervisor` 22 / `browser` 40 / `stream` 35 包），在独立隔离拓扑重跑并通过 `.scratch/t104_deploy_verify/verify_ac004.py`（Caddy/UI、关态、`[ext1, ext2]` 并发与自由扩展拒载、Free 模式 GTK3 Load unpacked 跨重启持久、切回关态停用、双受管 Profile 同扩展双向 `chrome.storage.local` 隔离与 Stream 零挂载）、`verify_ac005.py`（官方 Bitwarden CRX3 `2026.11.0` 经认证 CONNECT 代理与 `ghcr.io/dani-garcia/vaultwarden:alpine` 同步、Policy Agent 零直连阻断与 WebAuthn `navigator.credentials.create/get` 同 ID `juZvVKBATK6_3MIrUfvJOQ` Passkey 闭环）及 `verify_migration_and_restore.py`（`0016 -> 0017` ID/存储连续性与 `restore_point.py` 备份恢复），清理后无残留容器/网络/卷。
- review：`full` 级 Round 2 `overall=PASS`（`review_code.md` 与 `review_test.md` 均 `verdict: PASS`、`reviewed_scope: 0ce7fd1e4cb519c9`、`ac_review=ok`、`coverage = 3 / 5`；Round 1 全部 blocking 与测试 finding 均已消除，Round 2 Test 零新增，Code 唯一新增非阻断 `minor` `t104_code_f012` 遗留至 `p167`；两项 `[deploy]` AC 按规则标 `trust_prior` 建议合并前人工抽查）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 交付控制面受管扩展资产目录（`/api/v1/extensions` CRX3/CRX2/ZIP 解包与公钥身份派生、流式 ZIP 炸弹上限校验、图标安全输出及 `409 extension_in_use` 全引用删除保护，辅以并发锁与写事务内引用校验）。
- 交付 Profile 运行配置 `allow_extensions` + 有序 `extension_ids` 替换 `extension_paths`（旧键 422 拒绝）、`0017_managed_extensions.py`（`e10400170001`）fail-before-write 迁移与扩展 ID/存储连续性校验、前端有序多选/内联上传/风险提示 UI 与 OpenAPI/TS 同步。
- 交付 Supervisor 只读按环境扩展挂载（未绑定与 Stream 容器零可见）、Browser 优雅停机落盘、Runner 四态开关启动接管及 Free 模式开发者模式 `Load unpacked` 持久入口；`restore_point.py` 同步纳入受管扩展并跳过临时隐藏目录。
- 遗留：`p167`（非阻断 `minor` 高圈复杂度函数拆解清理）。

### 长期文档闭环

- 关联与受影响 spec（front matter `tasks` 均已登记 `t104`）：`docs/specs/profile_management.md`、`docs/specs/browser_isolation.md`、`docs/specs/storage_and_artifacts.md`、`docs/specs/ui_design_system.md`、`docs/specs/release_deployment.md`。
- 长期 blueprint 更新：`docs/blueprint/architecture.md`、`docs/blueprint/domain.md`、`docs/blueprint/browser_runtime.md`、`docs/blueprint/persistence.md`、`docs/blueprint/security.md`、`docs/blueprint/testing.md`。
- 前置 spike 与 verified finding 闭环：[`s029` report](../../spikes/s029_extensions_and_bitwarden_passkey/report.md) 已完结、事实沉淀于 [`d055`](../../findings/d055_extensions_and_bitwarden_passkey.md)（CRX3 密钥回填、`cloakbrowser` `IGNORE_DEFAULT_ARGS` 接管与 GTK3 `Load unpacked` 入口已全部由 `t104` 采纳落地，无需额外 follow-up）。
