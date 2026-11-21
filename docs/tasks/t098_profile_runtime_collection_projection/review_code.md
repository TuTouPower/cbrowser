# Task review t098（reviewer_focus: 代码）

- task：`t098_profile_runtime_collection_projection`
- spec：`docs/tasks/t098_profile_runtime_collection_projection/task.md`
- diff_anchor：`50df4f1a55393aae417a9ccae6116478c0e927ec`
- target：`git diff 50df4f1a55393aae417a9ccae6116478c0e927ec`
- round：1
- reviewed_at：2026-11-21T11:27:00+08:00

reviewed_scope: 4724bcf7599177ef

## Findings

### t098_code_f001 - 非成员行的筛选页失效没有任何新旧围栏，过期/重复事件仍可引发列表重取

- 严重度：minor
- 锚点：AC-002「重复或过期事件不引发列表重取」+ 一句话失败场景：集合读取已越过某事件后，迟到的同状态事件对筛选页非成员行反复触发重取（状态不倒退、最终仍收敛，仅多余请求）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:890-901`（`applyRuntimeEventToCollections` 非成员分支）
- 问题：成员行路径有完整围栏（`runtimeFenceAllows` 按 `state_revision` 判定 + `projectionsEqual` 去重，`useProfilesQuery.ts:904-916`），但非成员分支只看 `statusBucketIncludes(params.status, event.observed_state)` 就 `invalidateQueries`，不校验事件新旧。具体场景：HTTP 集合读取在 rev8（stopped）已越过某环境，迟到的 rev7（running）事件到达 `running_exact` 的 all-pages 缓存时，该环境是非成员且 running 在桶内 → 触发重取；该事件每次重放都再触发一次。另一面：SSE 建连时服务端对全部环境逐个下发初始快照事件（`src/backend/cbrowser/api/v1/router.py:185-242`），状态筛选页中每个「不在本页但在桶内」的环境都会命中此分支，使一次建连/重连对同一页产生多次失效。影响有界：重取结果由服务端权威收敛，已观测状态不倒退，故按 minor 报，不阻断 AC 主体成立。
- 建议：为非成员失效加水位围栏，例如按页记录已应用/已见的最大 `state_revision`（或每环境最近已知 revision），事件 revision 低于水位时跳过失效；或对快照驱动的失效做合并（同一轮事件处理内同一 queryKey 只失效一次）。

### t098_code_f002 - 全局协调器错误 alerts 的失效判定未过 revision 围栏，过期事件可触发多余重取

- 严重度：minor
- 锚点：AC-002「重复或过期事件不引发列表重取」/ AC-003「全局协调器错误仍能呈现和清除」+ 一句话失败场景：携带旧错误文案的迟到事件与当前 alerts 缓存不一致时触发 alerts 重取（重取后仍为服务端真相，横幅不会错误呈现或残留）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:1085-1100`（`useProfileEventsSync` 的 alerts 失效段）
- 问题：该段直接用 `event.last_coordinator_error` 与 alerts 缓存条目比较，未先经 `runtimeFenceAllows` 对该事件做新旧判定。成员行/runtime 缓存会正确丢弃的过期事件，若其错误文案与当前 alerts 缓存不同（例如错误已变更或已清除后又收到旧文案事件），仍会 `invalidateQueries(runtimeAlerts())` 引发一次重取。后果仅为多余请求：alerts 是服务端紧凑读模型，重取即收敛，不产生错误呈现，故 minor。
- 建议：先以该环境集合行或 runtime 缓存的 revision 围栏判定事件有效性，围栏未通过时跳过 alerts 失效；或改为在围栏通过的合并结果上比较错误文案。

## 结论

- 本轮新发现：2 条（minor 2，critical / important 0）
- 未进表的提示：
    - 文件过大（按降级规则只提示、不进表）：`src/frontend/src/features/profiles/useProfilesQuery.ts` 1472 行（本 task 净增 254 行，超实现源码 800 行 important 阈值）；`src/frontend/src/features/profiles/useProfilesQuery.test.tsx` 1223 行（净增 160 行，超测试 1200 行阈值）；`src/backend/cbrowser/adapters/database/repository.py` 3128 行（净增 51 行）、`src/backend/cbrowser/services/profile_service.py` 2283 行（净增 51 行）均为存量大文件继续净增。未见由体量直接导致的可观测缺陷。
    - 复杂度提示：`applyRuntimeEventToCollections`（`useProfilesQuery.ts:883`）手算圈复杂度约 10，达结论段提示级，未进表。
    - 范围外观察（非本 diff 引入，不进表）：`src/frontend/src/features/profiles/EnvironmentCard.tsx:32` 存量代码对缺失 runtime 的 `observed` 回落 `"stopped"`，仅影响「最后停止」文案行；状态徽标本身经 `environmentStatusDescriptor(undefined)` 正确呈现未知，本 task 未触及该文件、行为与基线一致。
    - 安全 / 契约 / 性能视角已扫：diff 无新增外部输入拼接、无凭证落盘或日志、无 CORS/鉴权变更；破坏性契约变更（删除 `/profiles/runtime-summary`、集合行模型换型、`ProxyUsedByEntry.observed_state` 改必填）均为 spec 明确要求，OpenAPI 与生成类型已同步再生，关联 spec 与 blueprint 已同步修订；服务端一页查询数固定（见 AC-004 复验）。
- 总体判断：实现真实落地了集合运行投影、单调 `state_revision` 围栏、筛选边界服务端收敛、紧凑 alerts 读模型与代理引用自带状态，四条 AC 打勾均有实现与测试支撑；仅存两条 minor（非成员/alerts 路径的多余重取），无未解决 critical / important，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。集合行自带可空运行投影（`src/backend/cbrowser/domain/models.py` 的 `ProfileCollectionItem`/`ProfileRuntimeProjection.from_runtime`、service 按页组合），列表经 `projectionToRuntime` 读行投影、缺投影保持 undefined 并由 `environmentStatusDescriptor` 呈现未知，操作结果经 `applyRuntimeResponseToCollections` 同围栏合并、预览按捕获时间单调合并；独立重跑后端 t098 测试 10/10、前端 EnvironmentListPage 等 4 文件 96/96 通过。
- AC-002：TICK-VALID，re_verified。集合读取/操作结果/SSE 事件共用 `state_revision` 围栏（`runtimeFenceAllows`，双侧都有 revision 时仅比 revision，同版本换实例与配置回滚均被吸收），各缓存按自身 revision 独立围栏，迟到事件不合成新行、不复活已删除环境，成员行重复事件零副作用——上述均见 `useProfilesQuery.test.tsx` 对应用例且独立重跑通过（该文件与 SessionEntryPage、EnvironmentSwitcher 共 32/32）；非成员失效未设围栏的残余多余重取见 f001（minor）。
- AC-003：TICK-VALID，re_verified。服务端状态桶与前端 `statusBucketIncludes` 逐项一致，跨越筛选边界时失效对应页由服务端收敛成员/总数（对应用例重跑通过）；会话入口以 `running_exact` 全页集合 + 行投影判定、starting 不挤占（SessionEntryPage.test 重跑通过）；切换器关闭不拉取任何状态、条目状态来自集合行（EnvironmentSwitcher.test 重跑通过）；代理 used-by 条目自带 `observed_state`（集成测试 `test_used_by_entries_carry_observed_state` 重跑通过）；协调器错误经集合行与 alerts 读模型呈现、收敛后清除（集成测试 `test_runtime_alerts_and_row_error` 与 AppLayout.shell.test 重跑通过）。
- AC-004：TICK-VALID，re_verified。独立重跑查询计数用例 `test_page_query_count_fixed_as_total_grows` 通过（环境总数 10→100、页大小固定时 runtime SELECT 数不变、总 SELECT 至多 +1），`list_runtimes_by_ids` 为页内 id 一次批量读；常驻横幅只读仅含错误环境的 alerts 模型，全库摘要端点已删除（集成测试断言 404 重跑通过）；列表、会话入口、切换器、代理引用均无逐行 runtime 请求（代码核查 + 上述组件测试通过）。

coverage = 4 / 4

verdict: PASS

## Round 2 (2026-11-21T12:06:37+08:00)

- task：`t098_profile_runtime_collection_projection`
- diff_anchor：`50df4f1a55393aae417a9ccae6116478c0e927ec`
- target：`git diff 50df4f1a55393aae417a9ccae6116478c0e927ec`
- round：2
- reviewed_at：2026-11-21T12:06:37+08:00

reviewed_scope: 0e7db4e696bf7703

## Findings

### t098_code_f003 - 新鲜度门只认 runtime 缓存一个见证：无该缓存时重复/过期事件仍引发集合页与 alerts 重取（f001/f002 修不彻底）

- 严重度：minor
- 锚点：AC-002「重复或过期事件不引发列表重取」+ 一句话失败场景：只看列表、从未打开详情的会话中，迟到或重复事件对筛选页非成员行反复触发重取（状态不倒退、最终仍由服务端收敛，仅多余请求，与第 1 轮定级一致）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:1136-1137`（`useProfileEventsSync` 的 `eventIsHistory` 计算）；非成员失效在 `src/frontend/src/features/profiles/useProfilesQuery.ts:937-947`、alerts 失效在 `src/frontend/src/features/profiles/useProfilesQuery.ts:1140-1157`
- 问题：本轮新增的新鲜度门以 per-profile runtime 缓存为唯一见证：`eventIsHistory = old != null && !runtimeFenceAllows(old, event)`。该缓存只在详情访问时填充，列表/会话常驻路径通常为空（`old == null`），此时抑制完全不生效——第 1 轮 f001 描述的主场景（SSE 建连/重连时服务端逐个下发初始快照、迟到事件命中筛选页非成员行）原样保留。另外见证存在时也只压住严格更旧的事件（`incoming.state_revision < cached.state_revision`）：与见证同 revision 的重复事件围栏判定为放行（`runtimeFenceAllows` 用 `>=`），非成员分支又没有成员分支的 `projectionsEqual` 去重，重复事件每次重放仍触发一次失效。alerts 段同理：无 runtime 缓存见证时，携带旧错误文案的迟到事件与 alerts 缓存不一致仍触发重取。新增用例「a stale event below the runtime cache revision triggers no collection or alerts invalidation」只覆盖见证存在且严格更旧的一种组合，其余组合无防护也无用例。
- 建议：把见证扩展为每环境最近已知 revision 的统一水位（例如从全部集合缓存行与 runtime 缓存取该环境的最大 `state_revision` 写入一处轻量记录），非成员失效与 alerts 失效都先查水位；重复事件（revision 与水位相等且状态相同）同样跳过失效。

### t098_code_f004 - 抑制失效时成员行跨越筛选边界被就地写回筛选页，成员与总数不再由服务端收敛

- 严重度：minor
- 锚点：AC-003「状态跨越当前筛选条件时，列表成员、匹配总数和分页均按服务端结果收敛」+ 一句话失败场景：被抑制的历史事件把行状态改出当前筛选桶后，该行仍留在筛选页且总数不变，直到一次无关的重取才恢复
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:966-975`（`applyRuntimeEventToCollections` 成员分支的边界处理）
- 问题：成员分支在 `wasIn !== isIn` 时原本失效整页交服务端收敛；本轮修复后，当 `suppressInvalidation` 为真（事件相对 runtime 缓存为历史，但相对该行自身 revision 围栏仍放行——两缓存 revision 不一致是代码注释自认的常态），代码落入就地写回分支，把已跨出筛选桶的行连同新状态写回该筛选页，`total` 也不变。具体场景：runtime 缓存 rev9=running、筛选页 `status=running` 的行 rev1=running，重放一条 rev5=stopped 的中间事件——相对 runtime 缓存是历史（抑制失效），相对行围栏放行（5≥1），合并后行变为 stopped 却仍留在 running 页中展示，总数仍计入它。修复前该路径会失效重取并收敛到服务端真相（rev9=running，行留页且状态正确）。影响有界（单行成员/状态暂时不一致、无数据丢失，后续任一重取即收敛），且与既有「各缓存按自身围栏」设计取舍相关，故 minor。
- 建议：抑制只应跳过「失效」这一副作用，不应把跨界行写回筛选页：跨界且被抑制时保持该行原样不动（不合并跨界结果），或把该行从筛选页就地移除并同步递减 `total`，二者取一，不要写回。

## 结论

- 前轮 finding 复核：
    - `t098_code_f001`（minor，非成员分支失效无围栏）：修不彻底。已修部分真实：`useProfileEventsSync` 新增 `eventIsHistory` 新鲜度门，事件相对 runtime 缓存严格更旧时压制集合页与 alerts 的失效副作用，新增用例断言该组合下 `invalidateQueries` 零调用，本人复跑通过。未修部分：见证仅限 runtime 缓存且只压严格更旧事件，列表常驻场景与重复事件仍可引发重取，见本轮 f003。
    - `t098_code_f002`（minor，alerts 失效未过围栏）：修不彻底。与 f001 共用同一新鲜度门：见证存在且事件严格更旧时 alerts 不再失效（同一新增用例覆盖）；无见证时旧文案迟到事件仍可触发 alerts 重取，见本轮 f003。
    - 测试审阅 `t098_test_f001`（important，旧快照晚于新事件在集合读取维度无防护）：已消除（代码轴复核）。生产侧新增 `mergeFetchedCollectionItems`（`src/frontend/src/features/profiles/useProfilesQuery.ts:116-132`），分页查询与 all-pages 查询的 queryFn 在响应落地时按行以 `runtimeFenceAllows` 合并投影——取缓存与响应中 revision 更高者、响应缺投影时保留缓存投影，成员/总数/配置字段仍取新响应；新增受控异步顺序用例（refetch 在飞 → 先派发 rev5 事件 → 以 rev1 旧页 resolve）断言行保持 rev5/running，本人独立复跑该文件通过。未引入整页覆盖或合成新行等回归。
    - 测试审阅 `t098_test_f002`–`f005`（minor）：均已按处置落地并经本人核查——代理弹层断言状态点类别（`ProxyListPage.test.tsx:748-751`，running=bg-success、stopped=bg-on-surface-muted）；切换器非当前条目按行投影断言状态点与 aria 标签且 `getRuntime` 仍只调用 1 次（`EnvironmentSwitcher.test.tsx:322-375`）；列表页 `runtime=null` 行断言呈现未知而非已停止（`EnvironmentListPage.test.tsx:695-710`）；查询恒定用例扩到 20/100/1000 三档且总 SELECT 改为精确相等断言（`tests/unit/test_t098_collection_projection.py:108-147`，本人复跑通过）。
- 本轮新发现：2 条（minor 2，critical / important 0）
- 未进表的提示：
    - 文件过大（按降级规则只提示、不进表）：`src/frontend/src/features/profiles/useProfilesQuery.ts` 1530 行（第 1 轮 1472 行，本轮修复再净增 58 行，持续超实现源码 800 行阈值）；`src/frontend/src/features/profiles/useProfilesQuery.test.tsx` 1359 行（第 1 轮 1223 行，再净增 136 行，超测试 1200 行阈值）；`src/backend/cbrowser/adapters/database/repository.py` 3128 行、`src/backend/cbrowser/services/profile_service.py` 2283 行与第 1 轮相同（本轮未再净增）。未见由体量直接导致的可观测缺陷。
    - 复杂度提示：`applyRuntimeEventToCollections`（`src/frontend/src/features/profiles/useProfilesQuery.ts:926`）手算圈复杂度约 11（本轮 +1 来自抑制分支），达结论段提示级，未进表。
    - 范围外观察（非本 diff 引入，不进表）：与第 1 轮相同，`EnvironmentCard.tsx:32` 存量回落行为未变；`repository.py` 新增的 `type: ignore[arg-type]`（used-by `observed_state`）与相邻 `kind=` 既有同款标注一致，实施方已在 progress 中说明，保持一致不另出 finding。
    - 安全 / 契约 / 性能视角已扫（本轮增量重点复核）：新鲜度门与落地合并均为纯前端缓存逻辑，无新增外部输入、无凭证/日志、无鉴权或 CORS 变更；后端增量为零（本轮修复只动前端与测试）；查询数由 AC-004 三档精确相等断言钉住，无 N+1 回归。
    - 门禁证据核对：`gate-t098-final4` 的 suites.tsv 与 progress 记录一致（protocol_drift_check / requirements_check / contract / design_lint / design_check / frontend_build exit 0；unit / integration / frontend_test 的 exit 1 均为 progress 已逐条定性的基线失败与负载 flake，含单跑通过记录），本轮未重跑全量门禁，按任务要求采信该证据并以定向复跑补强。
- 总体判断：第 1 轮测试 important（慢集合响应覆盖事件结果）已真实闭环且未引入整页覆盖类回归；代码轴两条 minor 修得一半（见证覆盖面不足、抑制分支的跨界写回），残余均为多余请求或单行暂时不一致，无未解决 critical / important，四条 AC 打勾仍成立，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实现与第 1 轮复验结论一致（集合行自带可空运行投影、缺投影呈现未知、操作结果同围栏合并、预览按捕获时间单调合并）；本轮新增证据：列表页 `runtime=null` 行「未知」前端断言已补齐（`EnvironmentListPage.test.tsx:695-710`），本人独立复跑 EnvironmentListPage 等 4 文件 94/94 通过。
- AC-002：TICK-VALID，re_verified。本轮重点复验的「旧快照晚于新事件」维度已闭环：`mergeFetchedCollectionItems` 在分页与 all-pages 两条落地路径按行 revision 围栏合并（`useProfilesQuery.ts:116-132`、`:140-156`、`:172-199`），受控异步顺序用例（在飞 refetch 中先到 rev5 事件、后落地 rev1 旧页，断言 rev5/running 不倒退）本人复跑通过；后端 t098 unit+integration 本人复跑 10/10 通过。重复/过期事件在非成员/alerts 路径仍有多余重取残余，属第 1 轮已定级的 minor 范畴（见 f003），不推翻本 AC 的状态不倒退与最终一致主体。
- AC-003：TICK-VALID，re_verified。筛选边界由服务端收敛、会话入口 `running_exact`、切换器不拉取候选状态、代理引用自带状态、协调器错误呈现与清除等证据与第 1 轮一致；本轮补强证据：切换器非当前条目状态点/aria 断言与代理弹层状态点断言均已落地并复跑通过（见前轮 finding 复核段）。抑制失效下跨界行就地写回的单行残余见 f004（minor），不推翻打勾。
- AC-004：TICK-VALID，re_verified。查询恒定用例已扩到 20/100/1000 三档且总 SELECT 与 runtime SELECT 均改为精确相等断言（`tests/unit/test_t098_collection_projection.py:108-147`），本人独立复跑通过；`list_runtimes_by_ids` 单次批量读、摘要端点删除、alerts 紧凑读模型与无逐行 runtime 请求等其余证据与第 1 轮一致。

coverage = 4 / 4

verdict: PASS
