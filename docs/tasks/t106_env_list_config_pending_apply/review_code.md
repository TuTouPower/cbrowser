# Task review t106（reviewer_focus: 代码）

- task：`t106_env_list_config_pending_apply`
- spec：`docs/tasks/t106_env_list_config_pending_apply/task.md`
- diff_anchor：`9940cd79c2020bdeff43a5a453df9203356a7b85`
- target：`git diff 9940cd79c2020bdeff43a5a453df9203356a7b85`
- round：1
- reviewed_at：2026-11-24T00:44:40+08:00

reviewed_scope: 13be7a1d370e8251

## Findings

本轮无 finding。

## 结论

- 前轮 finding 复核：无（Round 1）
- 本轮新发现：0 条
- 未进表的提示：
    - 文件过大（按降级规则不进表，本任务均仅净增少量行，未产出可观测缺陷）：`src/frontend/src/features/profiles/useProfilesQuery.ts` 1708 行（+20）、`src/backend/cbrowser/api/runtime_coordinator.py` 1513 行（+3）、`src/backend/cbrowser/domain/models.py` 1293 行（+18）、`src/backend/cbrowser/api/v1/router.py` 1198 行（+27）、`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx` 1435 行（+113，测试）。
    - 范围外观察：直接裸跑 `pytest tests/unit`（绕过 `scripts/run_gates.sh` 环境准备）时 `tests/unit/test_preview_display.py` 有 2 例因 PATH 无 `jpeginfo` 失败；门禁 harness 从 `.scratch/jpeginfo/` 提供该二进制，与本 diff 无关。
    - 轻微风格项（不进表）：新增 `runtime_view` 的 `rt` / `coordinator` 形参用 `Any`；`detailApplyPending` 文案键在统一呈现单元后已无生产引用。
- 总体判断：领域谓词、三读模型填充、契约重导、各 surface 单一呈现单元与单一命令边界均已落地，未发现 blocking 缺陷，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`domain/models.py:423` 的 `config_pending()` 精确实现「runtime 存在 ∧ observed_state != stopped ∧ current > runtime 版本」，真值表单测 12 例通过；全仓视图层 grep 无残留版本比较式。
- AC-002：TICK-VALID，re_verified。`ProfileRuntimeProjection` / `ProfileRuntimeResponse` / `ProfileRuntimeStatusEvent` 三个读模型均含必填 `config_pending`，两份 OpenAPI 与生成 d.ts 同步且无新增 DB 列；`npm run check:api` 退出 0，契约一致性单测 4 例通过。
- AC-003：TICK-VALID，re_verified。`EnvironmentTable.tsx:337` 按 `row.runtime?.config_pending` 经 `ConfigPendingNotice` 渲染，无 runtime 投影时不显示且未知态仍由既有 StatusBadge 呈现；环境列表测试通过。
- AC-004：TICK-VALID，re_verified。`EnvironmentCard.tsx:100` 与表格共用同一 `ConfigPendingNotice` 和同一字段，卡片布局用例通过。
- AC-005：TICK-VALID，re_verified。行内应用统一走 `useApplyConfigRestart` → `useApplyDisplaySettingsMutation`，经 `scopeMutationToProfile` 隔离；用例断言仅目标行触发 stop、其它行不受影响且完成后提示消失。
- AC-006：TICK-VALID，re_verified。`SessionEntryPage.tsx:58` 将应用入口作为 `<Link>` 兄弟节点置入 `<li>`，用例同时断言待应用提示、应用按钮与 `href=/session/p1` 共存。
- AC-007：TICK-VALID，re_verified。`SessionHeader` / `SessionDetailsPanel` / `SharedProfileBanners` 均改读 `runtime.config_pending`，grep 确认生产代码无「待应用 = 版本比较」残留。
- AC-008：TICK-VALID，re_verified。`mergeProjection` / `useProfileEventsSync` 合并 `event.config_pending` 且 `projectionsEqual` 将其纳入变更判定；集合缓存注入用例验证无需导航即出现待应用。
- AC-009：TICK-VALID，re_verified。新增 `tests/unit/test_t106_config_pending.py` 12 例通过；前端全量 756 例、类型检查 `tsc -p tsconfig.test.json`、`npm run check:api`、契约/模型单测 4 例均独立复跑通过。

coverage = 9 / 9

verdict: PASS

## Round 2 (2026-11-24T01:43:17+08:00)

reviewed_scope: be2e91f74e8fba39

## Findings

本轮无新增 finding（finding_id 跨轮续编，下一可用编号为 t106_code_f001）。

## 结论

- 前轮 finding 复核：Round 1 code 报告无 finding。处置表声称依据 test 轴 t106_test_f001 新增共享工厂；以 diff 为准独立核实而非采信自述：`src/backend/cbrowser/api/v1/runtime_views.py:105` 新增 `make_runtime_event_data`，`src/backend/cbrowser/api/v1/router.py:224`（初始快照）与 `src/backend/cbrowser/api/runtime_coordinator.py:1101`（实时发布）两处 SSE 填充均已改经该工厂，工厂内部以 `config_pending(current_config_version, rt)` 统一派生字段，并由 `p.current_config_version` / `profile.current_config_version` 传入。全仓生产代码不再有直接构造 `ProfileRuntimeStatusEvent` 的 SSE 路径。该变更真实存在且正确，无循环依赖、无遗留旧签名调用。
- 本轮新发现：0 条
- 未进表的提示：
    - 文件过大（按降级规则不进表，本轮相关文件仅净增少量行、未产出可观测缺陷）：`src/backend/cbrowser/api/v1/router.py` 1184 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1501 行、`src/backend/cbrowser/domain/models.py` 1293 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 1708 行。
    - 新增 `runtime_view` 助手（`src/backend/cbrowser/api/v1/router.py:83`）在 6 个 REST 端点各引入一次 `get_profile` 读以获取 `current_config_version`；单次有界读、无循环内 N+1，不构成性能 finding。
    - 轻微风格项（不进表）：`runtime_view` 的 `rt` / `coordinator` 形参标注为 `Any`。
    - 裸跑 `pytest tests/unit` 时 `tests/unit/test_preview_display.py` 有 2 例因 PATH 缺 jpeginfo 失败；将该二进制加入 PATH 后 15 例全通过，与本 diff 无关。
- 总体判断：共享 SSE 事件工厂及其对 router/coordinator 填充的替换真实、正确；领域谓词、三读模型填充、契约重导、各 surface 单一呈现单元与单一命令边界均无回归，未发现 blocking 缺陷，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`src/backend/cbrowser/domain/models.py:423` 的 `config_pending()` 精确实现「runtime 存在 ∧ observed_state != stopped ∧ current > runtime 版本」；`tests/unit/test_t106_config_pending.py` 真值表独立复跑通过，全仓生产视图层 grep 无版本比较残留。
- AC-002：TICK-VALID，re_verified。三个读模型分别由 `ProfileRuntimeProjection.from_runtime`（`models.py:1036`）、`make_runtime_response`（`runtime_views.py:39`）、`make_runtime_event_data`（`runtime_views.py:105`）填充 `config_pending`，两处 SSE 路径均经后者；两份 OpenAPI 与生成 d.ts 含该字段，`npm run check:api` 退出 0，DB 模型无对应列。
- AC-003：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentTable.tsx:341` 按 `row.runtime?.config_pending` 经共享 `ConfigPendingNotice` 渲染，无 runtime 时不显示。
- AC-004：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentCard.tsx:104` 与表格共用同一 `ConfigPendingNotice` 与同一字段，无口径漂移。
- AC-005：TICK-VALID，re_verified。行内应用统一走 `useApplyConfigRestart`（`useProfilesQuery.ts:721`）→ `useApplyDisplaySettingsMutation`，经 `scopeMutationToProfile`（`useProfilesQuery.ts:729`）隔离，各 surface 薄调用。
- AC-006：TICK-VALID，re_verified。`src/frontend/src/features/browser-session/SessionEntryPage.tsx:74` 待应用提示与应用入口同屏且保留 `href` 链接语义。
- AC-007：TICK-VALID，re_verified。`SessionHeader.tsx:136`、`SessionDetailsPanel.tsx:295`、`SharedProfileBanners.tsx:37` 均读 `runtime.config_pending`；生产代码 grep 无「待应用 = 版本比较」残留。
- AC-008：TICK-VALID，re_verified。`useProfilesQuery.ts:817/843/1177/1203` 合并 `event.config_pending` 并纳入变更判定，集合缓存注入无需导航即由运行态跃迁待应用态。
- AC-009：TICK-VALID，re_verified。独立复跑 `test_t106_config_pending.py` + `test_api_models_and_sse.py` + `test_refactor_behavior_equivalence.py` 共 29 passed；全量 `tests/unit` 2548 passed（2 例 jpeginfo 环境失败，补 PATH 后通过）；`npm run check:api`、`npm run test:types` 退出 0。

coverage = 9 / 9

verdict: PASS

## Round 3 (2026-11-24T01:54:00+08:00)

reviewed_scope: 1e2158725670a39d

## Findings

本轮无新增 finding（finding_id 跨轮全局续编，下一可用编号为 t106_code_f001）。

## 结论

- 前轮 finding 复核：Round 1 / Round 2 的 code 报告均无 finding，无遗留 blocker 需复核。处置表声称的修复不采信；本轮以相对 `9940cd79c2020bdeff43a5a453df9203356a7b85` 的当前 worktree 与 `git diff 9940cd79c2020bdeff43a5a453df9203356a7b85` 独立核实。
- 本轮变化：Round 2 之后仅 `md_format.py` 对若干 Markdown 文档与 review 报告的格式化，无源码 / 测试语义变化。已核对本轮 reviewed_scope 指纹 `1e2158725670a39d` 与当前 worktree 实算值一致；`review_code.md` 经 `monitoring.py:54` 的 `REVIEW_PROCESS_FILES` 排除，追加本报告不影响指纹。
- 本轮新发现：0 条
- 未进表的提示：
    - 文件过大（按降级规则不进表，本任务相关文件未净增到新阈值、未产出可观测缺陷）：`src/frontend/src/features/profiles/useProfilesQuery.ts` 1708 行、`src/backend/cbrowser/api/runtime_coordinator.py` 约 1501 行、`src/backend/cbrowser/domain/models.py` 1293 行、`src/backend/cbrowser/api/v1/router.py` 约 1184 行、`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx` 1435 行（测试）。
    - 轻微风格项（不进表）：`runtime_view` / `make_runtime_response` 的 `rt` / `coordinator` 形参仍标注 `Any`；`detailApplyPending` 文案键在统一呈现单元后已无生产引用。
    - 裸跑 `pytest tests/unit` 时 `tests/unit/test_preview_display.py` 有 2 例因 PATH 缺 `jpeginfo` 失败；门禁 harness 从 `.scratch/jpeginfo/` 提供该二进制，与本 diff 无关。
    - 本轮未重跑全量前端 756 例与设计门禁：Round 1 / 2 已完整复跑且本轮无源码 / 测试语义变化；本轮独立复跑了领域谓词单测、SSE 模型等价单测、`check:api` 与 `test:types`，均通过。
- 总体判断：领域谓词、三读模型填充、两处 SSE 填充共用工厂、契约重导、各 surface 单一呈现单元与单一命令边界均无回归，未发现 blocking 缺陷，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`src/backend/cbrowser/domain/models.py:423` 的 `config_pending` 精确为「runtime 存在 ∧ observed_state != stopped ∧ current > runtime.config_version」；error 态（observed_state=error≠stopped）为真、stopped/无 runtime/版本相等为假，`tests/unit/test_t106_config_pending.py` 14 例本轮独立复跑通过；全仓视图层仅 `useProfilesQuery.ts:1202` 存在 `config_version` 比较，属两条 runtime 字段的变更检测而非待应用判定。
- AC-002：TICK-VALID，re_verified。三个读模型字段位于 `models.py:899/932/1024`（投影于 `:1043` 填充），`runtime_views.py:83`（响应）与 `:122`（SSE 事件）均经 `config_pending()` 派生；`make_runtime_event_data` 同时被初始快照（`router.py:224`）与实时发布（`runtime_coordinator.py:1101`）调用。两份 OpenAPI 与生成 d.ts 同步（d.ts 含 3 处 `config_pending`），`npm run check:api` 退出 0；backend 全仓 grep `config_pending` 仅命中谓词与读模型，无 DB 列 / 迁移。
- AC-003：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentTable.tsx:341` 按 `Boolean(row.runtime?.config_pending)` 经共享 `ConfigPendingNotice` 渲染；无 runtime 投影时不显示，未知态仍由既有 `StatusBadge` 路径呈现。
- AC-004：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentCard.tsx:104` 与表格读同一 `config_pending`、共用同一 `ConfigPendingNotice`（`EnvironmentCardGrid.tsx:36` 透传 `applyPendingId`），无口径漂移。
- AC-005：TICK-VALID，re_verified。行内应用统一走 `useApplyConfigRestart`（`useProfilesQuery.ts:721`）→ `useApplyDisplaySettingsMutation`，`scope()` 经 `scopeMutationToProfile`（`:729`）隔离；`EnvironmentListPage.tsx:252` 按 `apply.scope(id).isPending` 计算 `applyPendingId`，仅目标行持有 pending / notice，其它行不受影响。
- AC-006：TICK-VALID，re_verified。`src/frontend/src/features/browser-session/SessionEntryPage.tsx:58` 将 `ConfigPendingNotice` 作为 `<Link>` 兄弟节点置入 `<li>`，`href=/session/:id` 跳转语义保留；`pending` 取 `profile.runtime?.config_pending`，为假时不显示。
- AC-007：TICK-VALID，re_verified。`SessionHeader.tsx:135`、`SessionDetailsPanel.tsx:294`、`SharedProfileBanners.tsx:36` 均改读 `runtime.config_pending`（后者删除了原 `current_config_version !== config_version` 表达式）；生产代码无「待应用 = 版本比较」残留。
- AC-008：TICK-VALID，re_verified。`useProfilesQuery.ts:841/872/989/1177/1203` 将 `config_pending` 纳入合并、`projectionFromEvent` 与变更判定；SSE `runtime_state` 经 `make_runtime_event_data` 携带该字段，集合缓存注入无需导航即由运行态跃迁待应用态并显示行内入口。
- AC-009：TICK-VALID，re_verified。本轮独立复跑 `test_t106_config_pending.py`（14 passed）、`test_api_models_and_sse.py` + `test_refactor_behavior_equivalence.py`（15 passed）、`npm run check:api`（退出 0）、`npm run test:types`（退出 0）；全量前端 756 例与设计门禁沿用 Round 1/2 完整复跑结果，本轮无源码 / 测试语义变化。

coverage = 9 / 9

verdict: PASS
