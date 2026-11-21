# Task review t101（reviewer_focus: 通用）

- task：`t101_profile_event_watermark_residual`
- spec：`docs/tasks/t101_profile_event_watermark_residual/task.md`
- diff_anchor：`0e2f379e69ca8ff24e01cf589fff7113e9cbc628`
- target：`git diff 0e2f379e69ca8ff24e01cf589fff7113e9cbc628`
- round：1
- reviewed_at：2026-11-21T15:03:51+08:00

reviewed_scope: 229a7ff56d9b3fa9

## Findings

### t101_gen_f001 - 新事件在 runtime 缓存存在时被误判为重复，集合页与 alerts 失效被整体吞掉

- 严重度：important

- 锚点：违反 AC-003「高于水位的新事件仍按既有路径更新成员行与失效筛选页」；可观测行为缺陷：一次真实的运行时状态跃迁（跨状态筛选边界且改变 coordinator error）在带 runtime 缓存的页面上不产生任何 `invalidateQueries`，筛选页与全局告警横幅保持旧值直到一次无关重取

- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:1203-1208`（先把事件写入 runtime 缓存）→ `:1222`（之后才计算见证）→ `:953`（用刚写完的 runtime 投影判 duplicate），叠加 `:1224-1229` 与 `:1233` 的 `eventIsSuppressed` 分支

- 问题：`useProfileEventsSync` 在事件处理顺序上先用 `old` + `runtimeFenceAllows` 把事件写回 runtime 缓存（`:1176-1208`），再调用 `revisionWitness`（`:1222`）。`revisionWitness` 的 runtime 分支（`:957-975`）因此读到的是**已被本事件改写过**的投影，其 `state_revision` 恰等于 `eventRevision`；当该投影其余字段与 `projectionFromEvent(event)` 一致时，`:953` 命中 `projectionsEqual`，`duplicate = true`，于是 `eventIsSuppressed = true`（`:1224-1226`），`applyRuntimeEventToCollections` 收到 `suppressInvalidation: true`，alerts 失效也被 `:1233` 跳过。

    reviewer 用真实 hook + `QueryClient` 复现：runtime 缓存 p1 rev1（`preview_captured_at: null`、`last_coordinator_error: "boom"`）+ `running_exact` 筛选页成员行 rev1 + alerts 条目 `"boom"`，投递 rev2 新事件（`observed_state: "stopped"`、`last_coordinator_error: null`）。结果 runtime 缓存正确推进到 rev2，但 `invalidateQueries` 调用数为 0——筛选页与 alerts 均未失效。后端 runtime 视图确实把 `preview_captured_at` / `last_started_at` 以 `null` 序列化（`src/backend/cbrowser/api/v1/runtime_views.py:81,93`），SSE 事件同样携带这些字段的空值，故该 equality 条件在生产可达，并非只在人造 fixture 下触发。

    现有测试未守护此路径：`:1039` 的跨边界失效用例与 `:1313` 的 alerts 失效用例都没有预置 per-profile runtime 缓存，见证里没有「被本事件改写过的 runtime 投影」，因而 `duplicate` 始终为 false，测试全绿但漏掉该回归。相对 t098 是行为倒退：旧逻辑 `eventIsHistory = old != null && !runtimeFenceAllows(old, event)` 对 rev2 > rev1 的新事件判 false，不会吞掉失效。

- 建议：在写 runtime 缓存**之前**计算见证（把 `revisionWitness` 调用提到 `:1176` 之前，或让见证读取改写前的 `old` 投影而非 `queryClient.getQueryData` 的当前值），使 `duplicate` 只反映「事件到达前已见过的投影」；并补一例预置 runtime 缓存的新事件用例，断言跨边界筛选页与 alerts 均被失效，锁定 AC-003。

## 结论

- 本轮新发现：1 条，important（blocking），无 critical
- 未进表的提示：f003/f004 两条目标修复本身成立——`revisionWitness` 聚合 runtime/全部集合行/WeakMap 水位使无 runtime 缓存时迟到与同修订重复事件被压制（AC-001），`applyRuntimeEventToCollections` 在抑制且跨边界时 `continue` 不再写回（`:1045-1056`，AC-002）；这两条我均确认非假绿。范围外改动未见（仅 blueprint/spec/progress/task 状态文档与两份前端交付文件）；未知契约清单为「无」，无残留 UNVERIFIED 标记；安全性、类型、契约·Breaking、性能（遍历全部集合缓存为 spec 风险段已明示）、健壮性视角无新增命中。新测试未用 `.skip` / 恒真断言 / mock 掉被测逻辑。
- 总体判断：f004 与 AC-001 修复到位，但 f003 的统一水位见证引入了一处新事件误判为重复的回归，直接违反 AC-003 且未获测试守护；存在未解决 important，判 FAIL。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。定向复跑 `useProfilesQuery.test.tsx` 27/27 通过；新增无 runtime 缓存迟到事件用例（`:1359` 起）断言集合页与 alerts 均不失效，同修订重复用例（`:1424` 起）由集合行 rev9 建立见证并断言不失效，见证确实来自集合缓存行而非 runtime 缓存。
- AC-002：TICK-VALID，re_verified。新增跨界成员行用例（`:1464` 起）预置 runtime rev9 与 rev1 成员行，投递被抑制的 rev5 停止事件，断言该行 `observed_state` 仍为 `running` 且筛选页未被失效；对照旧代码该分支会落入写回，用例非假绿；定向复跑通过。
- AC-003：TICK-VOID，re_verified。打勾不成立：reviewer 复现「runtime 缓存存在 + 高于水位的新事件」时见证在 runtime 缓存被本事件改写后计算（`:1203-1208` 早于 `:1222`），把新事件误判为重复，`invalidateQueries` 调用为 0，筛选页与 alerts 不失效，与「高于水位的新事件仍失效筛选页」直接冲突；现有失效用例均未预置 runtime 缓存，漏掉此路径。

coverage = 2 / 3

verdict: FAIL

## Round 2 (2026-11-21T15:10:49+08:00)

- task：`t101_profile_event_watermark_residual`
- spec：`docs/tasks/t101_profile_event_watermark_residual/task.md`
- diff_anchor：`0e2f379e69ca8ff24e01cf589fff7113e9cbc628`
- target：`git diff 0e2f379e69ca8ff24e01cf589fff7113e9cbc628`
- round：2

reviewed_scope: 2aa57a2d45d230f1

## Findings

### t101_gen_f002 - 新增的 f001 回归用例在旧（有缺陷）代码上同样通过，未真正锁住见证前移

- 严重度：minor
- 锚点：测试可信度（回归锁定缺口）；非 AC 违反、无行为缺陷——当前实现已正确，缺口仅在该用例无法区分「见证前移」与「见证滞后」
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:1520`（用例 `invalidates a filtered page and alerts for a fresh event with a runtime cache present`），runtime 缓存 fixture 在 `:1537-1549`，缺少 `preview_captured_at` / `last_started_at` / `last_stopped_at`
- 问题：该用例被声明为 f001 回归用例，但 reviewer 把 `revisionWitness` 临时移回 runtime 缓存写入之后（临时改动已按 SHA-256 `3e227b1c…` 原样恢复，源码零残留）后单独复跑，结果仍为 `1 passed | 27 skipped`。根因：fixture 的 runtime 缓存未设置三个时间戳字段（值为 `undefined`），而 `projectionFromEvent` 给它们填 `null`（`src/frontend/src/features/profiles/useProfilesQuery.ts:800-802`），`projectionsEqual`（`:854`）在 `undefined !== null` 时判 false——即使见证读到被本事件改写后的缓存也不会置 `duplicate`，新事件照常失效，用例在缺陷代码上依然为绿。Round 1 的真实复现（runtime 缓存显式 `preview_captured_at: null`，与后端 null 序列化一致）在当前实现上已复跑 1/1 通过，证明修复本身成立；仅该锁定用例不可靠。
- 建议：给用例的 runtime 缓存 fixture 补齐 `preview_captured_at: null`、`last_started_at: null`、`last_stopped_at: null`，使见证滞后时 `duplicate` 命中、用例转红；或交付前在基线（见证滞后）代码上做一次红灯验证。

## 结论

- 前轮 finding 复核：
    - t101_gen_f001（important，已消除）：以 diff 为准，见证计算已移到事件回调最前（`src/frontend/src/features/profiles/useProfilesQuery.ts:1131`），早于 runtime 缓存写入 `:1214-1219`、集合页写入 `:1225`、alerts 失效 `:1231` 与水位记录 `:1246`；所有见证输入均为事件前状态。reviewer 把 Round 1 复现场景（runtime 缓存显式 `preview_captured_at: null` + `running_exact` 成员行 + alerts `"boom"`，投递 rev2 停止事件）原样在当前代码复跑，由 Round 1 的 0 次失效变为筛选页与 alerts 均被失效，1/1 通过；定向全套 28/28 通过。前轮 blocker 真修，非采信处置表自称。
- 本轮新发现：1 条，minor
- 未进表的提示：实现层面未见新回归——见证前移后重连、落地合并、操作结果合并、预览同步用例仍随 28/28 通过；范围外改动未见（diff 文件集仍为 blueprint/spec/progress/task + 两份前端交付文件 + 本报告）；进度处置表按实施侧维护；未知契约清单「无」，无 UNVERIFIED 残留；安全性、类型、契约·Breaking、性能、健壮性视角本轮无新增命中。该 minor 仅影响回归锁定强度，不阻断。
- 总体判断：前轮 important 已真修且经独立复现验证，三条 AC 打勾均成立，本轮仅一条 minor 测试锁定缺口，无未解决 critical / important，本轮 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。定向复跑 28/28 通过；无 runtime 缓存迟到事件用例（`:1362` 起）断言集合页与 alerts 均不失效，同修订重复用例（`:1424` 起）由集合行 rev9 建立见证并断言不失效，见证来源为集合缓存行，未依赖 runtime 缓存。
- AC-002：TICK-VALID，re_verified。跨界成员行用例（`:1464` 起）预置 runtime rev9 与 rev1 成员行，投递被抑制的 rev5 停止事件，断言该行 `observed_state` 仍为 `running` 且筛选页未被失效；相对旧分支会落入写回，用例非假绿；定向复跑通过。
- AC-003：TICK-VALID，re_verified。见证已在任何缓存写入前计算（`useProfilesQuery.ts:1131`）；reviewer 用 Round 1 同一复现场景（runtime 缓存显式 `preview_captured_at: null`）独立复跑，新事件现在正确失效 `running_exact` 筛选页与 alerts（1/1 通过），原 0 次失效的缺陷已消除。新增声明用于锁定该场景的用例因 fixture 缺时间戳字段而不可靠，已记为 minor `t101_gen_f002`，不影响本 AC 实现判定。

coverage = 3 / 3

verdict: PASS

## Round 3 (2026-11-21T15:18:09+08:00)

- task：`t101_profile_event_watermark_residual`
- spec：`docs/tasks/t101_profile_event_watermark_residual/task.md`
- diff_anchor：`0e2f379e69ca8ff24e01cf589fff7113e9cbc628`
- target：`git diff 0e2f379e69ca8ff24e01cf589fff7113e9cbc628`
- round：3

reviewed_scope: 6610539d2d6cec18

## Findings

Round 3 零 finding。

## 结论

- 前轮 finding 复核：
    - t101_gen_f002（minor，已消除）：以 diff 为准，回归用例 `invalidates a filtered page and alerts for a fresh event with a runtime cache present`（`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:1520`）的 runtime 缓存 fixture 已补齐 `preview_captured_at: null` / `last_started_at: null` / `last_stopped_at: null`（`:1547-1549`）。reviewer 临时把 `revisionWitness` 调用移回 runtime 缓存写入之后（临时改动按 SHA-256 `3e227b1c…` 原样恢复，源码零残留），单独复跑该用例由 Round 2 的 `1 passed | 27 skipped` 翻为 `1 failed | 27 skipped`：`invalidateQueries` 调用数 0，失败于 `:1581`；当前交付代码定向 28/28 通过。该用例现已真正锁定 f001 修复，前轮 minor 真修，非采信处置表自称。
    - t101_gen_f001（important，Round 2 已消除，本轮复核保持）：见证仍在 `src/frontend/src/features/profiles/useProfilesQuery.ts:1131`、早于所有缓存写入；源码 SHA-256 在实验前后一致，未回退。
- 本轮新发现：0 条
- 未进表的提示：无。相对 Round 2 的交付内容仅多出该 fixture 三行，无新回归、无范围外改动、无危险测试模式（无 `.skip` / 恒真断言 / mock 被测逻辑）；未知契约清单「无」，无 UNVERIFIED 残留；安全、类型、契约·Breaking、性能、健壮性视角本轮均无新增命中。
- 总体判断：Round 1 的重要回归与 Round 2 的 minor 测试锁定缺口均已真修并经红灯/独立复现验证，三条 AC 打勾均成立，零 finding，本轮 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。定向复跑 28/28 通过；无 runtime 缓存迟到事件用例（`:1362` 起）断言集合页与 alerts 均不失效，同修订重复用例（`:1424` 起）由集合行 rev9 建立见证并断言不失效，见证来源为集合缓存行。
- AC-002：TICK-VALID，re_verified。跨界成员行用例（`:1464` 起）预置 runtime rev9 与 rev1 成员行，投递被抑制的 rev5 停止事件，断言该行 `observed_state` 仍为 `running` 且筛选页未被失效；相对旧写回分支非假绿；定向复跑通过。
- AC-003：TICK-VALID，re_verified。见证在缓存写入前计算（`useProfilesQuery.ts:1131`）；新增 f001 回归用例经基线红灯验证（见证滞后时 0 次失效、转红），当前实现下 28/28 全绿，新事件正确失效筛选页与 alerts。

coverage = 3 / 3

verdict: PASS
