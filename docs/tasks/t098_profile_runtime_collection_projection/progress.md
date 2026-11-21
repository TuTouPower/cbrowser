---
tid: "t098"
slug: "profile_runtime_collection_projection"
title: "环境列表与会话运行状态实时一致"
status: "done"
branch: "t098_profile_runtime_collection_projection"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "50df4f1a55393aae417a9ccae6116478c0e927ec"
spec_source_sha: "50df4f1a55393aae417a9ccae6116478c0e927ec"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 复现物缺失：task.md/p155 引用的 `.scratch/repro_create_status/`（Mac 本地 Vitest 复现，未入库）在云端仓不存在；按源码断裂点（集合页与全库摘要双读、行状态靠摘要合并、缺条目填「已停止」）自建回归测试，见 tests/unit/test_t098_collection_projection.py、tests/integration/test_t098_collection_projection_api.py 与前端 useProfilesQuery.test.tsx 的 t098 用例。
- 后端：`GET /profiles/collection` 行模型改为 ProfileCollectionItem（ProfileResponse＋可空 runtime 投影）；repo 新增 `list_runtimes_by_ids` 一次批量读、service 按页 id 组合投影、coordinator 错误在 service 内按同一 runtime 行收敛填充；删除 `/profiles/runtime-summary` 端点与 RuntimeSummary\* 模型及 service.list_runtimes；新增紧凑读模型 `GET /profiles/runtime-alerts`（仅含当前有协调器错误的环境，供全局横幅）；代理 used-by 条目随引用数据带 observed_state（repo 一次批量查）。
- 单调围栏：ProfileRuntimeResponse 与 ProfileRuntimeStatusEvent 增加 state_revision（DB 列既有、before_flush 每次写递增）；事件构造点（coordinator publish、SSE 初始快照）与 make_runtime_response 均已赋值。前端 runtimeFenceAllows 以 state_revision 为主围栏（双侧都有时仅比 revision，同版本换实例/配置回滚均被 revision 吸收），config_version＋instance 仅作旧端回退。
- 前端：删除 runtimeSummary 缓存/查询与 useRuntimeSnapshot 的 runningCount（无界面消费者）；事件同步改为就地合并所有已缓存集合页（含 all-pages 数组）＋按状态筛选边界失效收敛成员/总数、迟到事件不合成新行、重复/过期事件无副作用；预览事件改写集合行投影的 preview_captured_at（单调）；操作结果（setDesiredState/stop/apply）经 applyRuntimeResponseToCollections 同围栏合并；EnvironmentListPage 行状态直接读行投影、缺投影为显式未知；SessionEntryPage 用 running_exact 集合行的 runtime 判定；EnvironmentSwitcher 打开/关闭均不发批量状态读、状态来自 SessionPage 传入的集合行；ProxyUsedByPopover 读条目自带 observed_state；AppLayout 横幅改读 alerts，事件改变某环境错误时才失效 alerts。
- 契约迁移说明：t076 的 runtime-summary 集成测试（test_runtime_summary_single_payload）随端点删除而移除，其断言由 t098 新测试覆盖；前端多处 mock/夹具按新契约改写（摘要 mock 改为集合行投影/alerts），非改预期凑实现。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-21T11:27:16+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t098_code_f001|minor|已修|事件处理加 runtime 缓存新鲜度门，压制历史事件的非成员失效；残余覆盖面并入 Round 2 的 t098_code_f003|src/frontend/src/features/profiles/useProfilesQuery.ts（useProfileEventsSync）|
|t098_code_f002|minor|已修|同一新鲜度门压制历史事件的 alerts 失效；残余并入 t098_code_f003|src/frontend/src/features/profiles/useProfilesQuery.ts（useProfileEventsSync）|
|t098_test_f001|important|已修|集合页与 all-pages 落地按行 revision 围栏合并投影（mergeFetchedCollectionItems），新增受控异步顺序用例且经 reviewer 变异验证可红|src/frontend/src/features/profiles/useProfilesQuery.ts；useProfilesQuery.test.tsx|
|t098_test_f002|minor|已修|代理弹层用例补状态点 class 断言|src/frontend/src/features/proxies/ProxyListPage.test.tsx|
|t098_test_f003|minor|已修|切换器用例给非当前条目赋行投影并断言状态点/aria/单读次数|src/frontend/src/features/browser-session/EnvironmentSwitcher.test.tsx|
|t098_test_f004|minor|已修|列表页 stub 支持 runtime=null 行并断言呈现未知|src/frontend/src/features/profiles/EnvironmentListPage.test.tsx|
|t098_test_f005|minor|已修|查询恒定用例扩 20/100/1000 三档、总 SELECT 改严格相等|tests/unit/test_t098_collection_projection.py|

### Round 2 (2026-11-21T12:07:27+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t098_code_f003|minor|遗留|新鲜度门见证覆盖面残余（无 runtime 缓存时不生效、同 revision 重复仍可重取）；影响有界、重取后为服务端真相，两轮审阅均判 minor 不阻断|p158|
|t098_code_f004|minor|遗留|抑制失效时跨界行就地写回的单行收敛残余；下一次重取即收敛，两轮审阅均判 minor 不阻断|p158|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁两轮完整执行（证据 gate-t098-final3 / gate-t098-final4）＋修复后定向复验；unit 失败集与基线 50df4f1 逐条一致（云端环境基线），integration 与 frontend_test 的零星失败均逐条单跑复核为负载 flake，详见实施笔记各条
- 黑盒：不适用（云端无 Docker，CBROWSER_RUN_E2E 未启用；本 task 无 [deploy] AC）
- review：full 两轮——Round 1 code PASS / test FAIL（已修复），Round 2 code PASS / test PASS，四条 AC 全部 TICK-VALID
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 环境集合页改为行自带运行投影的单一读模型：删除全库 runtime-summary 端点与前端摘要缓存，新增 state_revision 单调围栏统一事件/集合读取/操作结果三路合并，新增紧凑 alerts 读模型承载全局协调器错误横幅；OpenAPI 与前端生成类型已同步，长期 spec/blueprint 已更新。遗留仅 p158（两条 minor 残余），正文见该条目。

### 长期文档闭环

- specs_index: 已在 docs/specs/profile_management.md、docs/specs/runtime_lifecycle.md、docs/specs/runtime_persistence.md 的 front matter `tasks` 清单登记 t098，并同步三处契约正文；docs/blueprint/architecture.md、domain.md、frontend.md 的运行投影口径已同步。本 task 无正式 spike。

## 门禁第一轮（云端）发现与处置

- unit 套件 2424 passed / 7 failed / 10 errors。其中两条为本 task 契约迁移需同步的既有测试（非改预期凑实现，断言语义不变）：
    - `tests/unit/test_api_models_and_sse.py::test_profile_runtime_status_event_exposes_font_set_state`：该用例对事件模型做全字段精确 dict 断言；事件契约按本 task 新增 `state_revision` 字段后，按 t076 为 `config_version` 扩此断言的同一先例补入 `"state_revision": 0` 一行，用例验证的字体集语义（t041 AC-007）不变。
    - `tests/unit/test_api_search_defaults.py`：其 `_runtime` SimpleNamespace 是运行读模型的测试替身，补 `state_revision=0` 镜像新读模型形状；被测的 search_defaults 实例围栏断言不变。此前替身缺字段使 `publish_profile_change` 在构造事件时 AttributeError 被广播边界吞掉、用例失败，属实现变更使替身形状过期。
- 其余失败（t063 built keyboard 系列 2 failed + 10 errors、t068 引擎工件 2 failed、t095 并发计时 1 failed）待与基线 50df4f1 对照定性后记录。
- 前端 frontend_test / frontend_build 两套件在门禁子进程里误用系统 Node 24（要求 >=26 \<27），属环境问题；最终轮门禁以 `mise exec` 包裹重跑。
- 基线对照定性（2026-11-21 云端实测）：在基线提交 50df4f1 的独立 worktree 上跑同一组可疑用例（test_t063_patched_keyboard_behavior、test_t068_engine_artifact_pinning、test_t095_probe_job_progress 的并发计时用例），得 5 failed + 10 errors，与本分支门禁中的失败集逐条比对完全一致（diff 为空）。定性：云端环境基线（t063 需已构建的 keyboard wheel manifest、t068 需引擎工件/Docker、t095 为负载下计时），非本 task 引入，不阻塞收尾。
- 门禁第一轮其余套件：protocol_drift_check / requirements_check / contract / design_lint / design_check / integration 全部 exit 0；unit 除上述基线与已修两条外 2424 passed。
- 前端套件门禁内 node 版本问题根因（2026-11-21 云端定位）：run_gates.sh 的 ensure_jpeginfo 按 PATH 找到系统 jpeginfo（/usr/bin/jpeginfo）后把其目录 /usr/bin 前置到 PATH 第一位，系统 Node 24.22.1 就此压过 mise 工具链 Node 26.13.0，frontend_test / frontend_build 的 check:node 预检（要求 >=26 \<27）必失败——与调用方 PATH 顺序无关，前两轮门禁这两套件的 exit 1 均为此环境机制，非代码问题。处置（不改仓库代码）：带外供给只含 jpeginfo 副本的目录 ~/workspace/cloud-task-logs/gate-tools 置于 PATH 首位（与 selkies wheel 缓存同款的带外供给机制；副本经 ensure_jpeginfo 的 d040 契约校验接受），门禁前置的改为该无害目录，npm 恢复解析到 mise Node 26。最终轮门禁（证据目录 gate-t098-final3）以此环境运行。
- 最终轮门禁（证据目录 gate-t098-final3）：protocol_drift_check / requirements_check / contract / design_lint / design_check / frontend_build 全部 exit 0。frontend_test 736 例过 735，唯一失败为 SettingsPage i18n 用例 5s 超时（与本 task 无关的设置页），单跑该文件 3/3 通过，定性负载 flake。unit 2426 passed，5 failed + 10 errors 与基线失败集逐条一致（见上）。integration 本轮 222 passed、1 failed + 8 errors（t052 测速作业 1 条 + supervisor 子进程类 8 条），全部 9 条逐条单跑通过，且同一代码在前两轮全量门禁中 integration 均为 exit 0；本轮 unit 耗时 758s（基线轮 581s）显示机器负载显著更高，定性负载 flake、非本 task 回归。

## 审阅轮 1 结论与修复（FAIL → 修复重验）

- review_code：PASS，2 条 minor（f001 非成员分支失效无围栏、f002 alerts 失效未过围栏）。
- review_test：FAIL，1 条 important（f001：AC-002「旧快照晚于新事件」在集合读取维度无防护——慢响应落地会整页覆盖事件合并结果）＋4 条 minor（f002 代理弹层状态点无断言、f003 切换器非当前条目状态无断言、f004 runtime=null 行未知呈现无前端断言、f005 查询恒定只在 10→100 验证且总查询留 +1 余量）。AC-002 被判 TICK-VOID，其余三条 TICK-VALID。按流程已撤回全部打勾后修复：
    - 生产修复（test f001）：集合页与 all-pages 查询落地时按行以 state_revision 围栏合并投影（mergeFetchedCollectionItems）——落地响应只带回成员/总数/配置字段，行投影取缓存与响应中修订更高者，缺投影不作删除解。新增受控异步顺序用例：refetch 在飞时事件先行合并、旧页后落地，断言行保持新修订不倒退。
    - 生产修复（code f001/f002）：事件处理加新鲜度门——事件修订低于 runtime 缓存已知修订时判为历史事件，压制其集合页失效与 alerts 失效副作用；字段合并仍按各行自身围栏进行（与既有「缓存各按自身围栏」用例相容，该用例保持绿）。
    - 测试补强（test f002–f005）：代理弹层断言状态点类别（running=bg-success、stopped=bg-on-surface-muted）；切换器断言非当前条目按行投影显示状态点与 aria 标签且不新增单读；列表页 stub 支持 runtime=null 行并断言呈现「未知」而非「已停止」；查询恒定用例扩到 20/100/1000 三档且总 SELECT 数改为精确相等断言（实测恒定）。
    - code reviewer 范围外观察（repository.py 新增 type: ignore[arg-type]）：与同函数相邻 kind= 行的既有同款标注一致（字典 .get() 宽类型），保持一致不另改。
- 修复后定向复验：useProfilesQuery 24/24、ProxyListPage＋EnvironmentSwitcher＋EnvironmentListPage 70/70、test:types 0 错误、后端 t098 unit 5/5（含三档计数）。全量门禁复验见下一轮记录。
- 全量门禁复验（证据目录 gate-t098-final4）：protocol_drift_check / requirements_check / contract / design_lint / design_check / frontend_build exit 0；frontend_test 740 例过 739，唯一失败 ConfigTab 保存回显用例 5s 超时，单跑 3/3 通过（负载 flake，与上一轮 SettingsPage 同签名）；unit 2425 passed，失败为基线 15 条＋t027 回滚就绪 1 条，单跑通过（本轮 unit 耗时 884s，负载显著）；integration 228 passed、0 failed、3 errors（test_normal_exit_replay 子进程类），整文件单跑通过。前两轮已定的基线与 flake 口径不变。
