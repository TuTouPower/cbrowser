---
tid: "t101"
slug: "profile_event_watermark_residual"
title: "修复 Profile 事件同步的陈旧/重复事件重取与跨界行写回"
status: "done"
branch: "t101_profile_event_watermark_residual"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "0e2f379e69ca8ff24e01cf589fff7113e9cbc628"
spec_source_sha: "0e2f379e69ca8ff24e01cf589fff7113e9cbc628"
depends_on: ""
conflicts_with: ""
note: "来源 p158（t098 review_code f003/f004，均 minor）；给事件同步加 per-profile 已见最高 revision 水位统一见证，抑制失效时跨界成员行不再写回筛选页。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-21：在登记 worktree `../cbrowser_t101` 实施。先建立三条失败用例（无 runtime 缓存的迟到非成员事件、同修订重复事件、抑制下跨界成员行），复跑确认 3 红 / 24 绿；再实现统一水位见证与跨界抑制分支，复跑 27/27 绿。
- 实现要点：`revisionWitness` 聚合 runtime 缓存、全部集合页（含 all-pages）行与按 QueryClient 隔离的持久水位（WeakMap），得出每环境最高已见 revision 及同修订同投影重复标记；`useProfileEventsSync` 据此统一压制集合页与 alerts 失效，事件处理后推进水位。`applyRuntimeEventToCollections` 成员分支在 `suppressInvalidation` 且跨越筛选边界时保持该行原样、不写回、不改总数。
- Round 1 review（important `t101_gen_f001`）：见证最初在 runtime 缓存被本事件改写**之后**计算，把新事件误判为自身重复，吞掉筛选页与 alerts 失效。修复：把见证计算提到任何缓存写入之前，并补一例「预置 runtime 缓存的新事件仍失效筛选页与 alerts」回归用例（定向 28/28 通过）。全量复跑 747/747。
- 门禁：`npm run test:types` 通过；前端全套 88 文件 / 746 用例通过；`design:lint` 0 error / 0 warning；`design:check` 一致；`npm run build` 与 Selkies dist 新鲜度校验通过；`git diff --check` 通过。黑盒不适用（纯前端缓存逻辑，无 `[deploy]` AC，与 t098 同口径）。
- 文档：`docs/specs/profile_management.md` 的 front matter `tasks` 追加 t101；`docs/blueprint/frontend.md` 记录统一水位与跨界不写回契约。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1（2026-11-21T15:03:51+08:00）

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t101_gen_f001|important|已修|见证改到缓存写入前计算，新事件不再自判重复；补预置 runtime 缓存的新事件失效回归用例，定向 28/28 通过|src/frontend/src/features/profiles/useProfilesQuery.ts:1125|

### Round 2（2026-11-21T15:10:49+08:00）

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t101_gen_f002|minor|已修|回归用例 runtime fixture 补齐 `preview_captured_at` / `last_started_at` / `last_stopped_at` 为 null，见证滞后时该用例转红，真正锁定修复|src/frontend/src/features/profiles/useProfilesQuery.test.tsx:1537|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`tsc -p tsconfig.test.json` 通过；Vitest 全量 88 文件 747/747 通过（含本 task 新增 4 例，先红后绿，Round 1 修复后再验）
- 黑盒：不适用——本 task 无 `[deploy]` AC，纯前端缓存同步逻辑由可控 SSE 事件流在 Vitest 中触达生产 hook 验证，与 t098 同口径
- review：Round 1 一条 important 真修并经独立复现验证；Round 2 PASS（一条 minor 测试锁定缺口）；Round 3 零 finding、PASS（机器门禁 general_verdict=PASS、overall=PASS、AC 复验 3/3 TICK-VALID）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 统一水位见证解决 t098 f003（无 runtime 缓存迟到/重复事件不再多余重取），跨界抑制不写回解决 f004；Round 1 reviewer 发现的新事件自判重复回归已修并锁定用例。

### 长期文档闭环

- `docs/specs/profile_management.md` front matter `tasks` 已登记 t101；`docs/blueprint/frontend.md` 已记录 t101 事件同步见证契约。
