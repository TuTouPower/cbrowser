# Task review t098（reviewer_focus: 测试）

- task：`t098_profile_runtime_collection_projection`
- spec：`docs/tasks/t098_profile_runtime_collection_projection/task.md`
- diff_anchor：`50df4f1a55393aae417a9ccae6116478c0e927ec`
- target：`git diff 50df4f1a55393aae417a9ccae6116478c0e927ec`
- round：1
- reviewed_at：2026-11-21T11:27:48+08:00

reviewed_scope: 4724bcf7599177ef

## Findings

### t098_test_f001 - AC-002「旧快照晚于新事件」在集合读取维度无受控异步顺序测试，且实现无防覆盖合并

- 严重度：important
- 锚点：AC-002「旧快照晚于新事件……已观测状态不倒退」；上下文区测试策略明确承诺「用受控的异步响应顺序测试集合初读、操作结果、重连和事件写入的竞争」
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:203`（seedCollection）与全部 t098 竞争用例；`src/frontend/src/features/profiles/useProfilesQuery.ts:116`
- 问题：全部 t098 竞争用例都是先用 `seedCollection`（`queryClient.setQueryData`）把缓存置为已读状态，再同步派发 SSE 事件；没有任何一条让 `listCollection` 请求处于 in-flight 时到达事件、再让该请求以事件之前的旧数据落地。生产侧 `useProfilesCollectionQuery` 的 queryFn 是裸 `listCollection(params)`（useProfilesQuery.ts:116），事件处理路径对 collection 缓存也没有 cancelQueries 或按 state_revision 合并落地结果的防护——in-flight 的慢响应落地时会整页覆盖事件已合并的新状态，已观测状态倒退，正是 AC-002 点名要防的场景。失败场景：列表聚焦触发 refetch → 请求未回时收到 running 事件并合并进行缓存 → 慢响应（服务端在事件前读到的 stopped 快照）落地覆盖 → 行回到 stopped 且 revision 围栏此后还会拒绝同 revision 的纠正事件。现有围栏测试只覆盖「旧事件晚于新缓存」，覆盖不到「旧快照响应晚于新事件」。
- 建议：补一条受控异步顺序测试（deferred 的 listCollection promise：发起读取 → 派发更新的事件 → 以旧快照 resolve 读取 → 断言行状态不倒退）；实现侧按 revision 合并 fetch 落地结果或在事件合并时取消 in-flight 的 collection 查询，测试须能红在当前实现上。

### t098_test_f002 - 代理弹层条目状态点已供数但无任何断言验证渲染

- 严重度：minor
- 锚点：AC-003「代理引用状态与对应环境一致」
- 位置：`src/frontend/src/features/proxies/ProxyListPage.test.tsx:658`（withUsedBy 夹具）与同文件 :728 弹层用例；`src/frontend/src/features/proxies/ProxyUsedByPopover.tsx:55`
- 问题：本轮 diff 给 used-by 夹具条目补了 `observed_state: "running"/"stopped"`，组件也按它渲染状态点（running → bg-success），但弹层用例只断言条目文本为名字「Beta」/「Gamma」，不断言状态点。若组件忽略 observed_state（例如恒显灰点），全部前端测试仍绿。数据交付本身已由后端集成测试 `test_used_by_entries_carry_observed_state` 验证，故仅记 minor。
- 建议：在弹层用例中对 p2/p3 条目的状态点 class 做一条断言（running 为 bg-success、stopped 为 bg-on-surface-muted）。

### t098_test_f003 - 切换器打开后非当前环境条目的真实状态无断言

- 严重度：minor
- 锚点：AC-003「打开后显示真实状态」
- 位置：`src/frontend/src/features/browser-session/EnvironmentSwitcher.test.tsx:104`（profile 夹具 `runtime: null`）与同文件 :318 起的 t098 用例；`src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx:82`
- 问题：切换器条目状态来自行投影 `profile.runtime?.observed_state`，但测试夹具所有 profile 的 runtime 恒为 null，t098 更新后的用例只断言触发器圆点（来自当前环境的单读）与「打开后不再发批量读取」，没有一条给非当前条目赋 running 投影并断言其状态点。条目状态渲染回归不会被现有测试捕获。会话入口与后端数据路径已另有覆盖，故记 minor。
- 建议：给一条非当前 profile 赋 `runtime: { observed_state: "running", ... }` 投影，打开弹层后断言其状态点为 bg-success。

### t098_test_f004 - 列表页无运行投影行（runtime=null）的「未知」呈现无前端断言

- 严重度：minor
- 锚点：AC-001「未取得运行事实时显示未知或加载」
- 位置：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:308`（listCollection stub 恒附加 projectionOf）
- 问题：后端已钉住数据契约（`tests/unit/test_t098_collection_projection.py::test_page_row_without_runtime_row_is_explicit_none` 断言 runtime 为 None 而非合成 stopped），但列表页测试的 stub 对每一行都附加投影，没有任何用例渲染 runtime=null 的行并断言状态呈现为未知；列表页「缺投影 → 显式未知」的接线回归无前端证据。
- 建议：在 EnvironmentListPage 测试中加一行 runtime=null 的环境，断言其状态单元格呈现未知文案而非「已停止」。

### t098_test_f005 - AC-004 查询恒定只在 service 层以总量 10→100 验证，与测试策略的 API 集成 20/100/1000 三档不符

- 严重度：minor
- 锚点：AC-004「获取一页所需配置和运行状态不随环境总量增加请求或查询次数」；上下文区测试策略「API 集成测试覆盖 20、100、1000 环境下的分页过滤、稳定排序和固定查询数」
- 位置：`tests/unit/test_t098_collection_projection.py:108`（test_page_query_count_fixed_as_total_grows）、同文件 :143
- 问题：固定查询数只在 service 层、总量 10→100、page_size=5 下验证；策略所述 API 集成层 20/100/1000 三档未落地（新增集成测试无规模/分页断言，分页过滤与稳定排序仅由 t076 既有小规模集成测试承载，本轮未改）。另总 SELECT 数断言留了 +1 余量（`<= small + 1`），虽不构成掩盖，但与「固定」口径不完全一致。AC-004 的核心语义（真实 DB、批量读、runtime SELECT 数严格相等）已验证，故记 minor。
- 建议：把查询数用例提升到 API 集成层并补 1000 档，或在 progress 中注明以 service 层验证替代三档的理由；总查询数断言改为严格相等或注明 +1 的来源。

## 结论

- 改测方向复核：无「迁就实现」的改测。逐项核对：`useProfilesQuery.test.tsx` 的 summary→collection 改写为契约迁移，断言等价或更强（新增「低 config_version、高 state_revision 的回滚事件应生效」与「高 config_version、低 revision 的迟到事件应被拒」两条比旧围栏更严的断言；删除的 running_count 断言对应已按 spec 移除的契约字段，其行为改由 SessionEntryPage 的 running_exact 请求断言与后端 `test_profiles_collection_status_running_exact` 承载）；`tests/integration/test_t076_collection_api.py` 删除的 `test_runtime_summary_single_payload` 对应 spec 明确移除的端点，其断言（config_version / instance / observed_state）由 t098 新集成测试 `test_collection_rows_carry_runtime_projection` 等价覆盖，属合法删除；`tests/unit/test_api_models_and_sse.py` 与 `tests/unit/test_api_search_defaults.py` 各加一行 `state_revision` 是契约字段扩展/替身形状同步，被测语义（字体集事件字段、search_defaults 围栏）未变；EnvironmentSwitcher「打开后读一次摘要」改为「打开后不再发批量读取」是新契约（状态随行交付）的必然结果，非迁就实现。
- 危险模式扫描：无 `.skip`/`.only`、无注释掉的断言、无恒真断言、无 timeout/重试放大、无条件跳过弱化断言、无 `.value =` 冒充交互；删除的 expect 均为已移除契约（runtime-summary / running_count）的断言且有等价替代（见上）。测试文件未新增 eslint-disable / @ts-ignore / type: ignore。
- 本轮新发现：5 条（important 1、minor 4）
- 未进表的提示：生产代码 `src/backend/cbrowser/adapters/database/repository.py` 本轮新增一行 `# type: ignore[arg-type]`（与上一行既有同款 ignore 相邻），属代码轴范围，提示 code reviewer 留意 observed_state 的类型收窄是否被掩盖。另：本人定向复跑时首批前端 3 文件曾出现 2 条失败，同批立即重跑 67/67 全过，与实施方记录的本机负载 flake 定性一致，不作为 finding。
- 总体判断：AC-002 点名的「旧快照晚于新事件」场景在集合读取维度既无测试也无实现防护，证据不足以支撑该 AC 的打勾，FAIL。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端新用例断言行投影随页交付、无运行记录行为显式 None、revision 随写递增（tests/unit/test_t098_collection_projection.py，本人复跑 5/5 过）；前端事件/操作结果按 revision 合并进行、列表状态直读行投影（useProfilesQuery.test.tsx、EnvironmentListPage.test.tsx，本人复跑全过）；仅 f004 一处 minor 证据缺口（未知呈现的 UI 断言），不推翻打勾。
- AC-002：TICK-VOID，re_verified。迟到/重复事件围栏、换实例、重连、已删除不复活、不重取均有真实测试且本人复跑全过，但「旧快照晚于新事件」在集合慢响应维度无任何受控异步顺序测试，且裸 queryFn 落地会整页覆盖事件合并结果（见 f001），该 AC 明列场景的证据不足，打勾不成立。
- AC-003：TICK-VALID，re_verified。筛选边界失效两用例、非成员进入 bucket 才失效、alerts 仅在协调器错误变化时失效（useProfilesQuery.test.tsx 新增用例）；会话入口 running_exact 且 115 行 starting 不挤占（SessionEntryPage.test.tsx 既有 f008 用例，本轮夹具已迁投影，本人复跑过）；切换器关闭/打开均不发批量读；后端集成验证 alerts 与行内错误一致、used-by 条目带 observed_state（本人复跑过）。f002/f003 为渲染断言 minor 缺口，数据与主路径证据充分。
- AC-004：TICK-VALID，re_verified。真实 DB 的 service 层用例断言总量 10→100 时 runtime SELECT 数严格不变、总 SELECT 数至多 +1（本人复跑过）；前端断言列表不调 per-profile getRuntime、切换器不发批量读、AppLayout 只读紧凑 alerts；规模档位与策略的偏差记 f005 minor，不推翻打勾。

coverage = 4 / 4

verdict: FAIL

## Round 2 (2026-11-21T12:06:50+08:00)

reviewed_scope: 0e7db4e696bf7703

## Findings

本轮零 finding。

## 结论

- 前轮 finding 复核：
    - t098_test_f001：已消除。生产侧 `mergeFetchedCollectionItems`（`src/frontend/src/features/profiles/useProfilesQuery.ts:116`）已接入分页集合 queryFn 落地路径（同文件 :148）与 all-pages 路径（同文件 :198）：落地响应只带回成员/总数/配置字段，行投影按 `runtimeFenceAllows` 取缓存与响应中修订更高者，缺投影不作删除解。新增受控异步顺序用例「a slow collection response landing after a newer event does not roll the row back」（`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:1180`）：deferred 的第二次 listCollection 在飞时先派发 revision 5 的 running 事件并断言已合并，再以 revision 1 的旧页 resolve，断言行保持 revision 5 / running。本人复跑该文件全过；另在 /tmp 副本中摘除落地合并做变异验证，该用例随即红在 revision 断言（expected 5），证明测试真实可红、非假绿。code 轴 f001/f002 的生产修复亦有对应新用例「a stale event below the runtime cache revision triggers no collection or alerts invalidation」（同文件 :1263），与生产侧历史事件门（useProfilesQuery.ts:1136 `eventIsHistory` 压制集合失效与 alerts 失效）对位，复跑通过。
    - t098_test_f002：已消除。弹层用例对 p2/p3 条目状态点断言 class（`src/frontend/src/features/proxies/ProxyListPage.test.tsx:743` 起：running 条目 `bg-success`、stopped 条目 `bg-on-surface-muted`），与组件渲染一致（`src/frontend/src/features/proxies/ProxyUsedByPopover.tsx:67` 状态点为条目按钮首个子元素 span，按 observed_state 取色）。本人复跑该文件全过。
    - t098_test_f003：已消除。新用例「打开后非当前环境按其行投影显示真实状态点」（`src/frontend/src/features/browser-session/EnvironmentSwitcher.test.tsx:322`）给非当前条目 p2/p3 赋 running/stopped 行投影，打开后断言 p2 状态点含 `bg-success` 且条目 aria-label 为运行文案、p3 不含 `bg-success`，并断言 `getRuntime` 全程只被当前环境 p1 调用一次。本人复跑该文件全过。
    - t098_test_f004：已消除。列表页 stub 支持 `noRuntimeIds`（`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:199`、:318），新用例「renders a row without a runtime projection as unknown, not stopped」（同文件 :699）断言 runtime=null 行状态单元格含未知文案且不含「已停止」。本人复跑该文件全过。
    - t098_test_f005：已消除（实质口径）。`tests/unit/test_t098_collection_projection.py:108` 查询恒定用例已扩到 20/100/1000 三档，总 SELECT 数与 runtime SELECT 数均改为严格相等断言（同文件 :141-149），原 +1 余量已去除。本人复跑该文件全过（含 1000 档建数）。仍在 service 层而非 API 集成层验证，但规模档位与「固定」口径已与测试策略一致；分页过滤与稳定排序由 t076 既有集成测试承载（第 1 轮已核），不构成 AC 证据缺口。
- 改测方向复核：无「迁就实现」的改测。本轮测试改动均为新增用例与断言补强；唯一的既有断言变更是查询数由 `<= small + 1` 收紧为严格相等（向更严方向）。生产行为先行变更（落地围栏合并、历史事件门），新测试断言的是 AC 语义而非实现输出的事后追认。
- 危险模式复扫：全 diff 新增测试行无 `.skip`/`.only`、无恒真断言、无注释掉的断言、无 eslint-disable/@ts-ignore/type: ignore、无 timeout/重试放大、无条件跳过弱化断言。
- 本轮新发现：0 条
- 未进表的提示：`mergeFetchedCollectionItems` 在落地行 runtime 为 null 时保留缓存投影；经查生产代码无「环境保留但运行行被删」的路径（运行行仅随环境创建/删除），该情形不落在任何 AC 场景内，仅提示 code reviewer 知悉此收敛语义。all-pages 落地合并与分页路径共用同一 helper，已由分页路径用例触达，无独立 all-pages 竞争用例，属可选扩展。
- 总体判断：前轮 1 条 important 与 4 条 minor 均以 diff 与复跑证据核实消除，本轮无新 blocker，四条 AC 打勾均有真实测试支撑，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。行投影随页交付、无运行记录行为显式 None、revision 随写递增（tests/unit/test_t098_collection_projection.py，本人复跑过）；f004 缺口已补：runtime=null 行在列表页呈现未知而非已停止（EnvironmentListPage.test.tsx:699，本人复跑过）；事件/操作结果按 revision 合并、预览仅按捕获事件更新的用例随 useProfilesQuery.test.tsx 本轮复跑全过。
- AC-002：TICK-VALID，re_verified。前轮缺口已闭环：受控异步顺序用例证明慢集合响应晚于新事件落地时行状态不倒退（useProfilesQuery.test.tsx:1180），且本人变异验证摘除生产合并后该用例变红；迟到/重复事件围栏、换实例、重连、已删除不复活、重复或过期事件不引发重取等既有矩阵随同文件本轮复跑全过（24/24）。
- AC-003：TICK-VALID，re_verified。筛选边界失效与成员收敛、会话入口 running_exact、alerts 仅在协调器错误变化时失效等既有证据本轮随相关文件复跑全过；f002/f003 渲染断言缺口已补（ProxyListPage.test.tsx:743 状态点 class、EnvironmentSwitcher.test.tsx:322 非当前条目状态点与 aria 标签），代理引用状态与对应环境一致、切换器打开后显示真实状态均有前端断言支撑。
- AC-004：TICK-VALID，re_verified。真实 DB 用例在 20/100/1000 三档下断言总 SELECT 数与 runtime SELECT 数严格恒定（tests/unit/test_t098_collection_projection.py:108，本人复跑过）；前端断言列表无每行单独运行读取、切换器不发批量读、AppLayout 只读紧凑 alerts，随本轮相关文件复跑全过；后端 t098 集成用例本人复跑 10/10（含 unit）通过。

coverage = 4 / 4

verdict: PASS
