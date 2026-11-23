# Task review t105（reviewer_focus: 测试）

- task：`t105_proxy_probe_expiry_auto_reprobe`
- spec：`docs/tasks/t105_proxy_probe_expiry_auto_reprobe/task.md`
- diff_anchor：`5715c0bddf5ae1097faf4ef0105f718cf23228f4`
- target：`git diff 5715c0bddf5ae1097faf4ef0105f718cf23228f4`
- round：1
- reviewed_at：2026-11-23T14:51:24+08:00

reviewed_scope: 6fb9756aa18056f2

## Findings

clean review，0 条。未发现恒真断言、弱化断言、删/反转 expect、注释掉断言、`.skip`/`.only`、静默错误抑制、mock 掉被测逻辑、阈值掩盖、条件跳过弱化断言或程序赋值替代真实交互。所有新增/改写测试均触达真实领域函数、真实 SQLite 仓储读路径、真实 Alembic 升级与真实 TestClient（HTTP），无 import 内部函数凑数或平行实现冒充覆盖。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 改测方向复核：本轮有 5 个既有测试文件被改写（`test_t052_egress_observation.py`、`test_t052_observation_repository.py`、`test_t076_collection_queries.py`、`test_t076_collection_api.py`、`test_t095_probe_job_progress.py`），另有 `test_t089_wrapped_snapshot_migration.py` / `test_t104_*` 的 head 常量机械更新。每处改写的归因均为 t105 规格变更本身——spec 明确要求「删除 TTL 跨越相关断言，新增任意时间点持续有效与端点/凭据变化失效断言」，旧断言的「过期 ok 隐藏」「`expires_at` 字段存在」语义被规格整体废弃，属于「新增覆盖新语义的测试 + 删除旧语义测试」，不是就地把预期改成当前实现的输出。无「迁就实现」的改测。
- 本轮新发现：0 条（clean review）。
- 未进表的提示：
    - `tests/unit/test_t052_egress_observation.py:61` 的 `test_observation_stays_current_across_any_point_in_time` 中，`observation_is_current` 已无时间参数，`observed_at` 取值对该函数结果无影响；该断言只证明「身份匹配时 ok 行 current」，与 `test_observation_current_when_endpoint_matches` 等价。真正的「任意时间仍为当前」由仓储层 `test_ok_observation_stays_current_across_any_time`（4000 天前 `observed_at` 落库后按真实读路径取回）承担。属可选覆盖精简，不改变行为覆盖，非 finding。
    - `tests/unit/test_t095_probe_job_progress.py` 改写后以 `all(item.observed_at is not None ...)` 取代旧的 `expires_at is not None` 断言；该断言因 `observed_at` 非空且必填而恒真，不是 AC 证据，本测试的有效证据是 `len(history) == 3`（历史行保留）。属可选断言增强，非 finding。
    - AC-004 的 collection/countries 一致性由 `test_t076_collection_queries.py::test_proxy_country_ranges_match_collection_current_observation` 在仓储层以国家/城市集合与筛选 ID 集合对齐验证；集成层 `test_proxy_candidates_and_countries` 只断言 `/proxies/countries` 的 JP/Tokyo，未直接对 `/proxies/collection` 的 `latency_ms` 做等价一致性断言。核心「无时间过滤 + 同口径」已被仓储层覆盖，此为可选扩展。
    - 前端未新增组件测试：t105 未改任何前端组件逻辑，TTL 仅为后端概念，前端 `.ts/.tsx` 全仓无 `expires_at` 引用；生成类型变更由既有 `npm run check:api`（OpenAPI→TS 漂移门禁，见 `test_a16_protocol_drift.py:348`）守护。AC-002 的界面展示属未变行为，由既有前端展示测试覆盖。
- 总体判断：6 条 AC 的打勾在测试与验证层均获真实支撑，改写测试归因清晰、无危险模式、可直接运行的针对性用例全绿（unit 94 passed、integration 5 passed），无未解决 critical / important，PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`git grep OBSERVATION_TTL_SECONDS`（排除 docs）无输出；全仓 `expires_at` 残留仅属 auth/session/AutomationToken 字段、历史迁移 `0001`/`0006` 与新迁移 0018 的 drop 语句及测试种子，均不在观测 AC 范围；两份 OpenAPI 与生成 `cbrowser_v1.d.ts` 的同批删除已在 diff 中核对，且 `npm run check:api` 漂移门禁（`test_a16_protocol_drift.py:348`）保证契约与生成类型同步。
- AC-002：TICK-VALID，re_verified。`tests/unit/test_t052_observation_repository.py::test_ok_observation_stays_current_across_any_time` 以 4000 天前 `observed_at` 的 ok 行写入真实 SQLite 后断言行状态/国家/IP 仍为当前；`::test_current_observation_survives_new_repository_instance` 用新建 `ProfileRepository` 对同一库重读（符合可测试性声明的「进程重启」替代验证）得到相同快照。两例均已实跑通过。
- AC-003：TICK-VALID，re_verified。`test_t052_egress_observation.py:83` 参数化断言 failed/pending 在身份匹配时为 current；`test_t052_observation_repository.py::test_endpoint_or_credential_change_invalidates_every_status` 以 3 状态 × 2 失配（endpoint/credential）经真实仓储读路径断言 `observation_status=="unknown"` 且国家/IP 为 None；已实跑通过。
- AC-004：TICK-VALID，re_verified。`test_t076_collection_queries.py::test_proxy_country_ranges_match_collection_current_observation` 断言 2 天前的 ok 行仍计入 JP/Tokyo（无时间过滤）、新 pending 行隐藏旧地理，并断言 `proxy_country_ranges` 与 `list_proxies_page(country_code="JP")` 的口径一致（cities == ["Osaka","Tokyo"]，page.total == 2 且 ID 集相同）；`test_t076_collection_api.py` 实跑 5 passed。
- AC-005：TICK-VALID，re_verified。`test_t105_observation_expiry_retirement.py` 用真实 Alembic 从 0017 升级至 head：断言 0017 时列存在、head 时列消失、仅一个 head、`alembic_version==b2c3d4e5f601`、历史行 `("obs-1",619,"JP","Tokyo")` 完整保留；downgrade 拒绝由 `test_t056_migrations.py::test_every_revision_downgrade_raises` 动态遍历全部 revision（含 0018）断言抛 `RuntimeError("not supported")` 覆盖；已实跑通过。
- AC-006：TICK-VALID，re_verified。`test_t095_probe_job_progress.py` 改写仅移除 `expires_at` 字段依赖并保留 `len(history)==3` 的历史保留断言，进度/并发/SSE 断言未动；连同 t089/t104 常量更新在内的 94 个相关 unit 用例实跑全绿，无回归。

coverage = 6 / 6

verdict: PASS

## Round 2 (2026-11-23T14:55:00+08:00)

Round 1 test 为 clean PASS（0 finding）。相对 Round 1，交付内容唯一变化是 `src/backend/cbrowser/adapters/database/repository.py:2372-2380` 中 `proxy_country_ranges` 的 docstring 文字修正（t105_code_f001 的处置），属描述性文字，不改任何测试逻辑、断言或生产代码路径；测试文件与 Round 1 完全一致。指纹由 `6fb9756aa18056f2` 更新为 `a35cbcf6290823ef`，已用 `task.py review-status` 的同源函数核对确认。

## Findings

clean review，本轮 0 条新 finding。相对 Round 1 唯一的交付变化是 repository.py 的 docstring，`observation_is_current` / `_visible_observation` / `_latest_observation_geo_subquery` 的签名与判定逻辑未动，未复引入恒真断言、弱化断言、删/反转 expect、注释断言、`.skip`/`.only`、静默错误抑制、mock 掉被测逻辑、阈值掩盖或条件跳过等危险模式。复验实跑：针对性 60 项（t052 领域/仓储、t076 collection queries/API、t095 进度、t105 迁移）全绿；迁移 downgrade 与契约漂移门禁 28 项全绿。

## 结论

- 前轮 finding 复核：Round 1 test 为 clean（0 finding），无 test finding 需复核；前轮 code f001（docstring）已由实施侧修正，本轮确认该修正仅为文字，未触及测试轴。
- 改测方向复核：相对 Round 1 无测试改动，本轮无「迁就实现」的改测。
- 本轮新发现：0 条（clean review）。
- 未进表的提示：沿用 Round 1 的 4 条可选扩展提示（`test_observation_stays_current_across_any_point_in_time` 与等价用例重复、t095 `observed_at is not None` 恒真但 `len(history)==3` 才是有效证据、集成层未对 collection/countries 的 `latency_ms` 做等价一致性断言、前端未新增组件测试而由既有 `check:api` 漂移门禁守护）。均非 finding，不改变行为覆盖，本轮不再展开。
- 总体判断：6 条 AC 的打勾在测试与验证层仍获真实支撑；相对 Round 1 唯一变化为 repository.py docstring，未触及测试逻辑，全部针对性用例复跑通过，无未解决 critical / important，PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`grep OBSERVATION_TTL_SECONDS` 在 src/schemas/tests/config 无输出；生成 d.ts 与两份 OpenAPI 残留的 `expires_at` 均位于 `AutomationTokenCreatedResponse` / `AutomationTokenResponse`（鉴权令牌过期字段），观测侧 `expires_at` 已删；`test_a16_protocol_drift.py` 契约漂移门禁本轮复跑通过。
- AC-002：TICK-VALID，re_verified。`test_t052_observation_repository.py::test_ok_observation_stays_current_across_any_time` 写入 4000 天前 ok 行经真实仓储读路径仍返回当前状态/国家/IP；`::test_current_observation_survives_new_repository_instance` 新建 `ProfileRepository` 重读同库快照一致，本轮复跑通过。
- AC-003：TICK-VALID，re_verified。`test_t052_egress_observation.py` 参数化断言 failed/pending 身份匹配时 current；`test_t052_observation_repository.py::test_endpoint_or_credential_change_invalidates_every_status` 以 3 状态 × 2 失配（endpoint/credential）经真实读路径断言状态 unknown、国家/IP 为 None，本轮复跑通过。
- AC-004：TICK-VALID，re_verified。`test_t076_collection_queries.py::test_proxy_country_ranges_match_collection_current_observation` 断言 2 天前 ok 行仍计入 JP/Tokyo（无时间过滤）、新 pending 隐藏旧地理，且 `proxy_country_ranges` 与 `list_proxies_page(country_code="JP")` 口径一致（cities `["Osaka","Tokyo"]`、page.total 2、ID 集相同）；`test_t076_collection_api.py` 本轮复跑通过。
- AC-005：TICK-VALID，re_verified。`test_t105_observation_expiry_retirement.py` 真实 Alembic 0017→head 断言列消失、单 head、`alembic_version==b2c3d4e5f601`、历史行 `("obs-1",619,"JP","Tokyo")` 完整保留；`test_t056_migrations.py::test_every_revision_downgrade_raises` 遍历含 0018 的全部 revision 断言 downgrade 抛错，本轮复跑通过。
- AC-006：TICK-VALID，re_verified。`test_t095_probe_job_progress.py` 改写仅移除 `expires_at` 依赖并保留 `len(history)==3`，进度/SSE 断言未动；连同 t089/t104 常量更新本轮针对性 60 项用例复跑全绿，无回归。

coverage = 6 / 6

reviewed_scope: a35cbcf6290823ef

verdict: PASS
