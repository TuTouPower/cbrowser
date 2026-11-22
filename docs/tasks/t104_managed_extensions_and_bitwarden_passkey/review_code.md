# Task review t104（reviewer_focus: 代码）

- task：`t104_managed_extensions_and_bitwarden_passkey`
- spec：`docs/tasks/t104_managed_extensions_and_bitwarden_passkey/task.md`
- diff_anchor：`41a4a3e848e673007090e4489beb0fbdb7ee5765`
- target：`git diff 41a4a3e848e673007090e4489beb0fbdb7ee5765`
- round：1
- reviewed_at：2026-11-23T01:48:46+08:00

reviewed_scope: 6432fd60c46b328f

## Findings

### t104_code_f001 - `ProfileService.update_profile` 仅传 `allow_extensions=True` 时未加载 `current` 触发 500 崩溃

- 严重度：important
- 锚点：`AC-002`（Profile 更新 API 支持 `allow_extensions` 与 `extension_ids`）；可观测行为缺陷：在编辑界面或 `PATCH /api/v1/profiles/{profile_id}` 仅传入 `{"allow_extensions": true}`（未同时修改 `extension_ids` 与 `fingerprint_platform` / `font_set_id`）启用自由模式时服务端抛出 `UnboundLocalError`（HTTP 500）。
- 位置：`src/backend/cbrowser/services/profile_service.py:753-805`；前端对应调用路径 `src/frontend/src/features/profiles/profile_field_diff.ts:37-50`
- 问题：`ProfileService.update_profile` 仅在第 753 行判断 `"fingerprint_platform" in patch_dict or "font_set_id" in patch_dict` 成立时才执行第 754 行 `current = await self._repo.get_profile(profile_id)`。当客户端通过 `diffProfileValues` 对已有 Profile 仅勾选「允许扩展」（从默认 `allow_extensions=false, extension_ids=[]` 切入自由模式，增量 PATCH 载荷为 `{"allow_extensions": true}`）时，代码跳过第 754 行直接进入第 799 行 `if "extension_ids" in patch_dict or patch_dict.get("allow_extensions") is True:`，并在第 803 行读取 `current.config.extension_ids`，触发 `UnboundLocalError: cannot access local variable 'current' where it is not associated with a value`。若同时传入 `fingerprint_platform` 但 `profile_id` 不存在，第 754 行返回 `current = None`，第 755 行跳过平台分支后第 803 行仍直接解引用 `current.config.extension_ids`，触发 `AttributeError: 'NoneType' object has no attribute 'config'`（返回 500 而非 404）。以上两条路径均已在隔离 SQLite 库直接复现。
- 建议：在缺少 `"extension_ids"` 且 `patch_dict.get("allow_extensions") is True` 时按需调用 `self._repo.get_profile(profile_id)` 加载 `current`，并在 `current is None` 时显式抛出 `ProfileNotFoundError(profile_id)`；为 `PATCH {"allow_extensions": true}` 及不存在 ID 补充集成测试。

### t104_code_f002 - `unpack_safe_zip_entries` 仅累加压缩包头未校验 `info.file_size`，存在 ZIP 炸弹内存耗尽风险

- 严重度：important
- 锚点：`AC-001`（扩展包上传与 API 边界校验）；可观测行为缺陷：构造小于 128 MiB 但 ZIP 目录头 `file_size` 伪造为小值的压缩包上传时，服务端会无界解压全量数据进内存，绕过 `MAX_EXTENSION_UNPACKED_BYTES`（256 MiB）上限导致内存耗尽（OOM DoS）。
- 位置：`src/backend/cbrowser/extensions/manifest.py:40-42,263-276`
- 问题：`unpack_safe_zip_entries` 在第 263 行仅把未受信任的 ZIP 目录头声明字段 `info.file_size` 累加进 `total_uncompressed` 与 `MAX_EXTENSION_UNPACKED_BYTES` 比较，随后在第 270 行直接调用无长度限制的 `content = zf.read(info)` 将整个压缩条目一次性解压入内存，既未使用剩余字节预算流式读取 `zf.open(info)`，也未按实际解压字节数 `len(content)` 校验与累计总预算。恶意包只需把头字段伪造为 `file_size=1` 即可膨胀到远超 256 MiB。
- 建议：通过 `zf.open(info)` 按剩余未解压预算 `remaining + 1` 分块读取条目内容并累计真实字节数 `actual_uncompressed`，一旦超出 `MAX_EXTENSION_UNPACKED_BYTES` 立即中断流并抛出 `ExtensionPackageError("invalid_extension_archive", ...)`。

### t104_code_f003 - 受管扩展删除、重导入与 Profile 绑定之间缺少锁保护与同事务引用校验，存在 TOCTOU 竞态

- 严重度：important
- 锚点：`AC-001`（受管扩展引用保护与资产完整性）；可观测行为缺陷：并发删除与重新导入同 `asset_id` 扩展或并发绑定扩展到 Profile 时，会出现数据库状态为 `verified` 但磁盘目录被误删、或 Profile 成功绑定已删除 `asset_id` 造成后续启动失败的悬空引用。
- 位置：`src/backend/cbrowser/services/extension_catalog.py:85-132,162-174`；`src/backend/cbrowser/adapters/database/extension_repository.py:309-322`；`src/backend/cbrowser/services/profile_service.py:618-626,805-820,1545-1556`
- 问题：存在两处并发时序窗口：1）`ExtensionCatalogService.delete_asset`（第 165-173 行）先在 `ExtensionAssetRepository.delete_if_unused` 的写事务中删库并提交，随后在无 per-asset 锁的情况下执行 `shutil.rmtree(ext_dir, True)`；若并发 `import_bytes`（第 85-111 行）对同一 `asset_id` 在删库提交后、`rmtree` 前执行，可跳过落盘或完成落盘并将 DB 重新 `upsert_verified` 为 `verified`，随后被滞后的 `rmtree` 清空磁盘目录。2）`ProfileService` 在 `create_profile`（第 618-626 行）、`update_profile`（第 805-820 行）和 `duplicate_profile`（第 1545-1556 行）中先以独立查询事务调用 `_validate_extensions` 校验存在性，再另开写事务落库 `extension_ids`；其间并发 `delete_asset` 的 `delete_if_unused`（第 315-318 行）仍观测到 0 引用并删除资产与目录，导致 Profile 悬空引用不存在的 `asset_id`。
- 建议：在 `ExtensionCatalogService` 中按 `asset_id` 持有 `asyncio.Lock` 串行化 `import_bytes` 与 `delete_asset` 的磁盘/数据库临界区，并在 `ProfileRepository.create_profile` / `update_profile` 同一写事务内复核 `extension_ids` 均处于已验证状态后再提交。

### t104_code_f004 - `ExtensionLibrarySection` 前端弹出层直接暴露 `#display_number`，违反 Spec 不变量

- 严重度：important
- 锚点：违反 `docs/specs/profile_management.md:127` 不变量（同时见 `docs/blueprint/frontend.md:80`）。
- 位置：`src/frontend/src/features/extensions/ExtensionLibrarySection.tsx:56-58`
- 问题：`docs/specs/profile_management.md:127` 规定「Profile 创建时后端分配部署内唯一显示编号（`display_number`），用于对应 Docker 沙箱容器名；前端界面不向用户直接暴露 `#0001` 编号」，同仓 `src/frontend/src/features/proxies/ProxyUsedByPopover.tsx:73` 也只渲染 `{entry.name}`。而 `ExtensionLibrarySection.tsx:56-58` 在扩展「Used by」列表直接渲染 `#{entry.display_number} {entry.profile_name}`，把内部容器显示编号暴露到了前端界面。
- 建议：删除 `#{entry.display_number}` 展示，仅渲染 `{entry.profile_name}`（与 `ProxyUsedByPopover.tsx:73` 保持一致）。

### t104_code_f005 - `ExtensionAssetRepository._reference_map` 在循环内逐条查询快照（N+1 查询）

- 严重度：minor
- 锚点：性能·资源（循环内查库）
- 位置：`src/backend/cbrowser/adapters/database/extension_repository.py:244-257`
- 问题：在汇总运行实例绑定版本的扩展引用时，第 246-254 行在 `for pid, ver in bound_pairs:` 循环内对每组 `(pid, ver)` 单独执行一次 `SELECT ProfileConfigVersionModel.snapshot`（N+1 查询），随活跃运行 Profile 数量线性放大查询往返次数。
- 建议：改用 `sa.tuple_(ProfileConfigVersionModel.profile_id, ProfileConfigVersionModel.version).in_(bound_pairs)` 单次批量查询全部目标版本快照。

### t104_code_f006 - `ExtensionLibrarySection` 硬编码 `"Bound"` 徽章文案与声明未使用 props

- 严重度：minor
- 锚点：i18n 一致性与死代码清理
- 位置：`src/frontend/src/features/extensions/ExtensionLibrarySection.tsx:70-76,214-216`
- 问题：第 215 行硬编码英文 `<StatusBadge tone="running" label="Bound" />` 未走 `t(...)` 本地化（同组件其余文案均走 `i18n.tsx`）；第 71-75 行声明的可选 props `selectedIds` 与 `onUploaded` 在组件体内未被任何逻辑消费。
- 建议：在 `src/frontend/src/i18n.tsx` 补齐中英文词条并改用 `t(...)`，清理未使用的 `selectedIds` / `onUploaded` props（或明确接线）。

### t104_code_f007 - Profile 变更成功后未失效前端 `extensionKeys` 查询缓存

- 严重度：minor
- 锚点：前端缓存一致性
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:315-317,339-341,352-354,400-402,435-437,1393-1396`（参考 `src/frontend/src/app/providers.tsx:60` 默认 `staleTime: 5000`）
- 问题：创建、更新、删除、批量删除完成与复制 Profile 的成功回调只调用 `invalidateProfileLists(queryClient)`，未失效 `extensionKeys.all`，导致在 `staleTime: 5000` 窗口内设置弹窗中的扩展 `used_by_count` 与可删除状态短暂滞后。
- 建议：在上述 Profile 变更回调中同步执行 `queryClient.invalidateQueries({ queryKey: extensionKeys.all })`。

### t104_code_f008 - `ExtensionCatalogService.adopt_existing` 在异步生命周期内同步读盘并跨模块导入私有辅助函数

- 严重度：minor
- 锚点：性能·IO（async 中同步 IO）与模块边界
- 位置：`src/backend/cbrowser/services/extension_catalog.py:220-254`；`src/backend/cbrowser/adapters/database/extension_paths_migration.py:30-32`
- 问题：`adopt_existing` 在异步 `lifespan` 启动路径中直接执行同步 `self._extensions_root.iterdir()`（第 220 行）和 `{rel: (entry / rel).read_bytes() for rel in verdict["file_hashes"]}`（第 245-248 行），将所有扩展文件同步读入事件循环线程；此外第 239-243 行及 `extension_paths_migration.py:30-32` 均直接导入 `manifest.py` 的私有函数 `_load_locale_messages`、`_pick_icon_relpath`、`_resolve_i18n_field`。
- 建议：在 `manifest.py` 提供公开元数据提取 helper（仅读取 `manifest.json`、`_locales/` 与图标路径，无需读取整个扩展目录），并将目录枚举与磁盘读取整段放进 `asyncio.to_thread`。

### t104_code_f009 - `restore_point.py` 备份受管扩展目录未过滤 `.staging-*` 残留临时目录

- 严重度：minor
- 锚点：健壮性与边界条件
- 位置：`scripts/restore_point.py:313-328`（对照 `src/backend/cbrowser/extensions/manifest.py:528`）
- 问题：`materialize_extension_directory` 会在 `extensions_root` 内创建 `.staging-{prefix}-{pid}` 临时目录；`restore_point.py:create_point` 仅跳过 symlink 与非目录，会把异常残留的 `.staging-*` 或非 64 位 sha256 目录一并写入 `manifest_extensions` 并复制进恢复点。
- 建议：在遍历 `extensions_dir` 时跳过以 `.` 开头的隐藏目录，并校验目录名符合受管资产 ID 格式。

### t104_code_f010 - `d055` 与 `s029` 新增/修改文档未通过 `md_format.py --check` 格式门禁

- 严重度：minor
- 锚点：文档与门禁一致性（`docs/blueprint/conventions.md:46`、`docs/blueprint/testing.md:149`）
- 位置：`docs/findings/d055_extensions_and_bitwarden_passkey.md`；`docs/spikes/s029_extensions_and_bitwarden_passkey/report.md`
- 问题：运行 `python3 .repo_template/scripts/md_format.py --check` 报 `格式漂移：docs/findings/d055_extensions_and_bitwarden_passkey.md, docs/spikes/s029_extensions_and_bitwarden_passkey/report.md`。
- 建议：执行 `python3 .repo_template/scripts/md_format.py` 对上述两份文档重新格式化。

### t104_code_f011 - 多处新建或在本 task 增加分支的函数圈复杂度 `CC >= 15`

- 严重度：minor
- 锚点：圈复杂度标准（`CC >= 15` 且新建或在本 task 新增分支/嵌套）
- 位置：
    - `src/backend/cbrowser/extensions/manifest.py:548` `verify_extension_directory`（CC=33，新建）、`:411` `parse_extension_archive`（CC=20，新建）、`:318` `_resolve_i18n_field`（CC=18，新建）、`:157` `_select_crx3_pubkey`（CC=16，新建）、`:355` `_pick_icon_relpath`（CC=15，新建）
    - `src/backend/cbrowser/adapters/database/extension_paths_migration.py:291` `_match_legacy_entry`（CC=23，新建）、`:408` `audit_extension_paths_database`（CC=21，新建）、`:161` `load_trusted_managed_catalog`（CC=20，新建）
    - `src/backend/cbrowser/runtime_agent/stealth_launch.py:52` `launch_stealth_persistent_context`（CC=19，新建）
    - `src/backend/cbrowser/supervisor/core.py:2965` `start_profile`（CC 37→38，+1）、`:2212` `_reconcile_instance_observation`（CC 20→21，+1）、`:2912` `_validate_extensions`（CC=19，新建）
    - `src/backend/cbrowser/supervisor/docker_adapter.py:2229` `start_browser_container`（CC 17→22，+5）
    - `scripts/restore_point.py:570` `restore_point`（CC 31→39，+8）、`:249` `create_point`（CC 19→23，+4）
- 问题：上述新建函数及在本 task 新增分支的现有函数圈复杂度均超过 15，单函数内聚合多层文件校验、快照解析或容器组装分支，后续修改易漏分支或引入状态分叉。（同属 `CC >= 15` 的 `ProfileService.update_profile` [16→19]、`ExtensionAssetRepository._reference_map` [19]、`ExtensionCatalogService.adopt_existing` [15] 已分别在 `t104_code_f001`、`t104_code_f005`、`t104_code_f008` 按具体缺陷立项。）
- 建议：将目录校验、归档解包、快照匹配/重写及容器扩展挂载拼装拆分为职责单一的小 helper，降低单函数分支密度。

## 结论

- 本轮新发现：11 条（4 条 important，7 条 minor）
- 未进表的提示：
    - **文件过大（降级至结论段，按实际行数 `wc -l` 且本 task 净增/新建达标列出）**：
        - `src/` 实现源码 `>= 800` 行：`src/backend/cbrowser/adapters/database/repository.py`（3067 行，net +4）、`src/backend/cbrowser/api/app.py`（842 行，net +6）、`src/backend/cbrowser/api/v1/router.py`（1185 行，net +1）、`src/backend/cbrowser/domain/models.py`（1278 行，net +92）、`src/backend/cbrowser/runtime_agent/runner.py`（1208 行，net +60）、`src/backend/cbrowser/services/profile_service.py`（2331 行，net +48）、`src/backend/cbrowser/supervisor/core.py`（3620 行，net +79）、`src/backend/cbrowser/supervisor/docker_adapter.py`（3087 行，net +37）、`src/frontend/src/features/profiles/useProfilesQuery.ts`（1683 行，net +57）、`src/frontend/src/i18n.tsx`（1239 行，net +44）。
        - `src/` 实现源码 `400–799` 行：`src/backend/cbrowser/adapters/database/extension_paths_migration.py`（612 行，新建）、`src/backend/cbrowser/adapters/database/models.py`（655 行，net +37）、`src/backend/cbrowser/extensions/manifest.py`（682 行，新建）、`src/backend/cbrowser/fingerprint_verification/probe_collector.py`（637 行，net +2）、`src/frontend/src/shared/api/client.ts`（775 行，net +43）。
        - 手写脚本 `400–799` 行：`scripts/restore_point.py`（798 行，net +59）。
        - 测试源码 `>= 1200` 行：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx`（1322 行，net +2）、`src/frontend/src/features/profiles/useProfilesQuery.test.tsx`（1579 行，net +2）；`600–1199` 行：`src/frontend/src/features/browser-session/SessionPage.test.tsx`（734 行，net +1）、`src/frontend/src/features/profiles/ProfileForm.test.tsx`（1027 行，net +126）、`src/frontend/src/features/proxies/ProxyListPage.test.tsx`（1139 行，net +1）、`tests/integration/test_api_subprocess.py`（869 行，net +1）。
        - 排除项（自动生成产物）：`schemas/openapi/cbrowser_internal.json`、`schemas/openapi/cbrowser_v1.json`、`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`。
    - **圈复杂度 `10 <= CC < 15` 与非生产/未扩分支函数提示**：
        - `10 <= CC < 15`：`scripts/restore_point.py:411` `validate_point`（9→11）、`src/backend/cbrowser/adapters/database/extension_paths_migration.py:227` `_inspect_legacy_directory`（13）与 `:356` `_resolve_extension_list`（11）、`src/backend/cbrowser/adapters/database/extension_repository.py:78` `_extract_extension_ids`（10）、`src/backend/cbrowser/extensions/manifest.py:192` `extract_crx_archive`（10）/ `:221` `_normalize_zip_relpath`（10）/ `:234` `unpack_safe_zip_entries`（10）/ `:661` `resolve_extensions_root`（10）、`src/backend/cbrowser/runtime_agent/runner.py:182` `_resolve_extension_paths`（10）、`src/backend/cbrowser/supervisor/docker_adapter.py:2657` `cleanup_container_by_name`（10→11）。
        - 本 task 触及但未增加分支的历史 `CC >= 15` 函数：`repository.py` `create_profile`（15）/ `update_profile`（18）、`api/app.py` `create_app`（59）/ `lifespan`（18）、`runner.py` `start`（27）。
        - 排除项（一次性 spike 探测脚本，非运行时源码）：`docs/spikes/s029_extensions_and_bitwarden_passkey/code/probe.py`（`test_spike1` 14、`test_spike2` 15、`_handle` 13、`start` 13）、`probe_bitwarden_passkey.py`（`main` 27、`start` 17、`_handle_any` 17、`_interact_bitwarden_fido` 11）。
- 总体判断：存在 4 个 blocking（`important`）缺陷——`ProfileService.update_profile` 开启 `allow_extensions` 的 500 崩溃、`unpack_safe_zip_entries` 仅信任头长度的 ZIP 炸弹风险、扩展资产删除/导入/绑定无锁 TOCTOU 竞态以及前端直接暴露 `#display_number`——必须修复后重新审阅。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已核对 `src/backend/cbrowser/extensions/manifest.py`、`src/backend/cbrowser/services/extension_catalog.py`、`src/backend/cbrowser/adapters/database/extension_repository.py`、`src/backend/cbrowser/api/v1/extensions_router.py` 实现并复跑 `t104` 扩展、迁移、OpenAPI/字段分类契约等后端用例（7 个测试文件共 44 passed），ZIP 炸弹解压预算绕过与并发删除/绑定 TOCTOU 缺陷分别见 `t104_code_f002` 与 `t104_code_f003`（关联界面编号暴露违约见 `t104_code_f004`）。
- AC-002：TICK-VOID，re_verified。已核对 `src/backend/cbrowser/services/profile_service.py`、`src/backend/cbrowser/adapters/database/extension_paths_migration.py`、`src/backend/migrations/versions/0017_managed_extensions.py` 与 `src/backend/cbrowser/runtime_agent/runner.py` 并复跑迁移/OpenAPI/字段分类用例，但实测直接复现 `ProfileService.update_profile` 在仅传 `{"allow_extensions": true}`（未带 `extension_ids` 与 `fingerprint_platform`/`font_set_id`）时抛出 `UnboundLocalError`（HTTP 500），且不存在 Profile 传平台与 `allow_extensions=True` 时抛 `AttributeError`，无法完整满足 AC-002 的 `allow_extensions` 更新 API 语义（`t104_code_f001`）。
- AC-003：TICK-VALID，re_verified。已核对 `ProfileForm.tsx`、`ProfileExtensionsSelector.tsx`、`profile_field_diff.ts`、`client.ts`、`profile_field_classification.ts` 与 `schemas/openapi/` 契约并复跑 `design:lint`（0 error / 0 warning）、`design:check`、`check:api`、`test:types` 与 Vitest（88 files / 749 passed）。
- AC-004：TICK-VALID，trust_prior。已核对 `supervisor/core.py`、`docker_adapter.py`、`volume_spec.py`、`runner.py` 与 `stealth_launch.py` 的只读挂载和四态/自由模式启动参数实现，真实有头容器内四态行为、跨 Profile/Stream 存储隔离与开发者模式安装持久化行为依赖交付验证脚本与结果证据 `.scratch/t104_deploy_verify/verify_ac004.py` 与 `.scratch/t104_deploy_verify/ac004_results.json`。
- AC-005：TICK-VALID，trust_prior。已核对容器内浏览器代理与扩展启动链路未设置直连绕过参数，真实有头容器与代理链路下 Bitwarden 官方扩展登录同步及 WebAuthn Passkey 注册/登录验证依赖交付验证脚本与结果证据 `.scratch/t104_deploy_verify/verify_ac005.py` 与 `.scratch/t104_deploy_verify/ac005_results.json`。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: FAIL

## Round 2 (2026-11-23T02:32:00+08:00)

reviewed_scope: 0ce7fd1e4cb519c9

### Findings

#### t104_code_f012 - Round 2 修复新增/增支后圈复杂度达 `CC >= 15` 的函数

- 严重度：minor
- 锚点：圈复杂度标准（`CC >= 15` 且新建或本 task 新增分支/嵌套）
- 位置：
    - `src/backend/cbrowser/services/profile_service.py:746` `update_profile`（CC 16→23，+7；`t104_code_f001` 缺陷已修复，当前增量分支来自按需预读 `current` 与异常映射）
    - `src/backend/cbrowser/adapters/database/repository.py:698` `update_profile`（CC 18→21，+3；事务内增补 `_assert_verified_extensions_in_tx` 守卫分支）
    - `src/backend/cbrowser/extensions/manifest.py:434` `extract_directory_metadata`（CC=15，新建）
- 问题：Round 2 修补使上述 3 个函数达到或高于 `CC >= 15` 阈值，长函数内部集中多类条件分支，后续维护仍偏重。
- 建议：可将 `update_profile` 的前置校验与事务校验及 `extract_directory_metadata` 的文件收集逻辑进一步拆出独立小 helper。

### 结论

- 前轮 finding 复核：
    - `t104_code_f001`：已消除。`src/backend/cbrowser/services/profile_service.py:758-771,815-821` 已在缺少 `extension_ids` 且 `allow_extensions is True` 时按需加载 `current`，并在 `current is None` 时抛出 `ProfileNotFoundError(profile_id)`；独立复现已通过（`REPRO_FIXED_OK`）。
    - `t104_code_f002`：已消除。`src/backend/cbrowser/extensions/manifest.py:239-264,296-305` 新增 `_read_bounded_zip_entry`，改以 `zf.open(info, "r")` 流式分块读取并按真实解压字节数累计 `total_uncompressed`，超限即抛出 `ExtensionPackageError("invalid_extension_archive", ...)`。
    - `t104_code_f003`：已消除。`src/backend/cbrowser/services/extension_catalog.py:30-42,100-148,181-190,269` 新增按 `(loop_id, resolved_root, asset_id)` 共享的 `_shared_asset_lock` 串行化 `import_bytes`、`delete_asset` 与 `adopt_existing`；`src/backend/cbrowser/adapters/database/repository.py:64-90,275,775-781` 在 `create_profile` / `update_profile` 同一写事务内调用 `_assert_verified_extensions_in_tx`，`profile_service.py:628-631,837-840,1583-1592` 将 `MissingExtensionReferenceError` 映射为 422 `ReferenceValidationError`。
    - `t104_code_f004`：已消除。`src/frontend/src/features/extensions/ExtensionLibrarySection.tsx:58` 已移除 `#{entry.display_number}`，仅渲染 `{entry.profile_name}`。
    - `t104_code_f005`：已消除。`src/backend/cbrowser/adapters/database/extension_repository.py:238-275` 已改为 `tuple_(ProfileConfigVersionModel.profile_id, ProfileConfigVersionModel.version).in_(bound_pairs)` 单次批量查询。
    - `t104_code_f006`：已消除。`src/frontend/src/features/extensions/ExtensionLibrarySection.tsx:16-78,200-210` 已移除硬编码 `"Bound"` 徽章与未使用的 `selectedIds` / `onUploaded` props。
    - `t104_code_f007`：已消除。`src/frontend/src/features/profiles/useProfilesQuery.ts:317,342,356,405,441` 已在 Profile 创建、更新、删除、批量删除完成与复制回调中同步失效 `extensionKeys.all`。
    - `t104_code_f008`：已消除。`src/backend/cbrowser/services/extension_catalog.py:20,233-271` 将目录枚举与磁盘检验/元数据读取整体移入 `asyncio.to_thread`，`extension_catalog.py:242` 与 `src/backend/cbrowser/adapters/database/extension_paths_migration.py:31,108` 改调 `manifest.py:434` 公开 helper `extract_directory_metadata`。
    - `t104_code_f009`：已消除。`scripts/restore_point.py:61,251-280` 提取 `_backup_extensions_dir`，跳过 `.` 开头隐藏目录（含 `.staging-*`）、symlink、非目录及不匹配 `MANAGED_EXTENSION_ID_RE` 的条目。
    - `t104_code_f010`：已消除。`python3 .repo_template/scripts/md_format.py --check` 对 `docs/findings/d055_extensions_and_bitwarden_passkey.md`、`docs/spikes/s029_extensions_and_bitwarden_passkey/report.md` 及相关 blueprint/spec/task 文档输出 `格式一致`。
    - `t104_code_f011`：修不彻底（非阻断 `minor`）。Round 1 所列 15 处函数中已有 12 处拆分降至 `< 15` 或增量 `<= 0`（`manifest.py` 原 5 处、`extension_paths_migration.py` 原 2 处、`stealth_launch.py`、`supervisor/core.py` `_validate_extensions` 与 `_reconcile_instance_observation`、`docker_adapter.py` `start_browser_container`、`restore_point.py` `create_point`）；仍余 `extension_paths_migration.py:293` `_match_legacy_entry`（CC=23）、`supervisor/core.py:2968` `start_profile`（CC 37→38）与 `scripts/restore_point.py:617` `restore_point`（CC 31→35）高于 15。
- 本轮新发现：1 条（0 条 blocking，1 条 minor：`t104_code_f012`）
- 未进表的提示：
    - **文件过大（按当前 `wc -l` 且本 task 净增/新建达标列出）**：
        - `src/` 实现源码 `>= 800` 行：`src/backend/cbrowser/adapters/database/repository.py`（3107 行，net +44）、`src/backend/cbrowser/api/app.py`（842 行，net +6）、`src/backend/cbrowser/api/v1/router.py`（1185 行，net +1）、`src/backend/cbrowser/domain/models.py`（1278 行，net +92）、`src/backend/cbrowser/runtime_agent/runner.py`（1208 行，net +60）、`src/backend/cbrowser/services/profile_service.py`（2362 行，net +79）、`src/backend/cbrowser/supervisor/core.py`（3623 行，net +82）、`src/backend/cbrowser/supervisor/docker_adapter.py`（3088 行，net +38）、`src/frontend/src/features/profiles/useProfilesQuery.ts`（1688 行，net +62）、`src/frontend/src/i18n.tsx`（1239 行，net +44）。
        - `src/` 实现源码 `400–799` 行：`src/backend/cbrowser/adapters/database/extension_paths_migration.py`（617 行，新建）、`src/backend/cbrowser/adapters/database/models.py`（655 行，net +37）、`src/backend/cbrowser/extensions/manifest.py`（789 行，新建）、`src/backend/cbrowser/fingerprint_verification/probe_collector.py`（637 行，net +2）、`src/frontend/src/shared/api/client.ts`（775 行，net +43）。
        - 手写脚本 `>= 800` 行：`scripts/restore_point.py`（821 行，net +82）。
        - 测试源码 `>= 1200` 行：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx`（1322 行，net +2）、`src/frontend/src/features/profiles/useProfilesQuery.test.tsx`（1643 行，net +66）；`600–1199` 行：`src/frontend/src/features/browser-session/SessionPage.test.tsx`（734 行，net +1）、`src/frontend/src/features/profiles/ProfileForm.test.tsx`（1112 行，net +211）、`src/frontend/src/features/proxies/ProxyListPage.test.tsx`（1139 行，net +1）、`tests/integration/test_api_subprocess.py`（869 行，net +1）。
        - 排除生成物：`schemas/openapi/cbrowser_internal.json`、`schemas/openapi/cbrowser_v1.json`、`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`。
    - **圈复杂度 `10 <= CC < 15` 与增量 `<= 0` / 排除提示**：
        - `10 <= CC < 15`：`scripts/restore_point.py:458` `validate_point`（9→11）、`src/backend/cbrowser/adapters/database/extension_paths_migration.py:229` `_inspect_legacy_directory`（13）/ `:358` `_resolve_extension_list`（11）/ `:454` `_audit_single_snapshot_row`（12）、`src/backend/cbrowser/adapters/database/extension_repository.py:90` `_extract_extension_ids`（10）、`src/backend/cbrowser/extensions/manifest.py:197` `extract_crx_archive`（10）/ `:226` `_normalize_zip_relpath`（10）/ `:362` `resolve_i18n_field`（11）/ `:668` `_validate_manifest_bytes`（12）/ `:768` `resolve_extensions_root`（10）、`src/backend/cbrowser/runtime_agent/runner.py:182` `_resolve_extension_paths`（10）、`src/backend/cbrowser/runtime_agent/stealth_launch.py:101` `launch_stealth_persistent_context`（12）、`src/backend/cbrowser/supervisor/core.py:2937` `_validate_extensions`（11）、`src/backend/cbrowser/supervisor/docker_adapter.py:2257` `start_browser_container`（17→14，已降支）/ `:2658` `cleanup_container_by_name`（10→11）。
        - 本 task 触及但 CC 增量 `<= 0` 的历史 `CC >= 15` 函数：`scripts/restore_point.py:312` `create_point`（19→19）、`repository.py:218` `create_profile`（15→15）、`api/app.py:220` `create_app`（59→59）/ `:240` `lifespan`（18→18）、`runner.py:561` `start`（27→27）、`supervisor/core.py:2212` `_reconcile_instance_observation`（20→19）。
        - 排除一次性 spike 脚本：`docs/spikes/s029_extensions_and_bitwarden_passkey/code/*.py`。
- 总体判断：Round 1 全部 4 项 blocking 缺陷与 6 项常规 `minor` 均已真实修复，当前无未解决的 `critical` / `important` 缺陷（仅余低复杂度的 `t104_code_f011` 部分项与 `t104_code_f012` 非阻断 `minor`），代码实现达到交付标准。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已核对 `_read_bounded_zip_entry`、`_shared_asset_lock`、`_collect_bound_runtime_refs` 批量查库与 `adopt_existing` 异步读盘等 Round 2 修复，复跑 `t104` 扩展及契约迁移后端用例（12 个测试文件共 124 passed）并验证伪造 `file_size` 压缩包拦截。
- AC-002：TICK-VALID，re_verified。已核对 `ProfileService.update_profile` 按需加载 `current`、`ProfileRepository._assert_verified_extensions_in_tx` 事务校验、迁移与 `runner.py` 实现，直接复验 `update_profile(p.id, {"allow_extensions": True})` 与不存在 ID 均通过预期（`REPRO_FIXED_OK`）且 124 passed。
- AC-003：TICK-VALID，re_verified。已核对 `ExtensionLibrarySection.tsx` 移除 `#display_number` / `"Bound"` 硬编码 / 未使用 props 与 `useProfilesQuery.ts` 同步失效 `extensionKeys.all`，并复跑 `design:lint`（0 error / 0 warning）、`design:check`、`check:api`、`test:types` 与 Vitest（88 files / 752 passed）。
- AC-004：TICK-VALID，trust_prior。已核对只读挂载与四态/自由模式启动控制代码实现，真实有头容器内四态、跨 Profile/Stream 存储隔离与开发者模式安装持久化行为依据 Round 2 重建后重跑的交付验证脚本与结果证据 `.scratch/t104_deploy_verify/verify_ac004.py` 与 `.scratch/t104_deploy_verify/ac004_results.json`。
- AC-005：TICK-VALID，trust_prior。已核对容器内浏览器代理与扩展启动链路未设置直连绕过参数，真实有头容器与代理链路下 Bitwarden 官方扩展登录同步及 WebAuthn Passkey 注册/登录验证依据 Round 2 重跑的交付验证脚本与结果证据 `.scratch/t104_deploy_verify/verify_ac005.py` 与 `.scratch/t104_deploy_verify/ac005_results.json`。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS
