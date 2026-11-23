# Task review t105（reviewer_focus: 代码）

- task：`t105_proxy_probe_expiry_auto_reprobe`
- spec：`docs/tasks/t105_proxy_probe_expiry_auto_reprobe/task.md`
- diff_anchor：`5715c0bddf5ae1097faf4ef0105f718cf23228f4`
- target：`git diff 5715c0bddf5ae1097faf4ef0105f718cf23228f4`
- round：1
- reviewed_at：2026-11-23T14:50:18+08:00

reviewed_scope: 6fb9756aa18056f2

## Findings

### t105_code_f001 - `proxy_country_ranges` docstring 仍描述已删除的 TTL 过期口径

- 严重度：minor
- 锚点：文档与实现不一致（diff 相关）；非 AC 行为缺陷，不阻断
- 位置：`src/backend/cbrowser/adapters/database/repository.py:2375-2379`
- 问题：该方法 docstring 写明「t076 review f004: aggregate over the same 'latest and still valid' rows the collection filter uses ..., so a country whose latest ok observation expired no longer offers a dead option that filters to zero rows」。t105 已彻底删除 TTL 与 `expires_at`（`src/backend/cbrowser/domain/egress_observation.py:38-54`、`src/backend/cbrowser/adapters/database/repository.py:2215-2257`），当前实现不存在「ok 观测过期」状态，聚合口径改为「每代理最新行 + status ok + 国家码非空、无时间过滤」。同一文件 `_latest_observation_geo_subquery` 的新注释已按此更新，唯独此处遗留旧 TTL 成因说明，误导后续维护者以为仍存在时效过滤。AC-001 的字面 grep（常量/字段名）不受影响。
- 建议：把 docstring 改为与 `_latest_observation_geo_subquery` 新注释一致的口径，删除 "expired" 措辞及 TTL 失效解释。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：1 条（minor）。
- 未进表的提示：`repository.py` 3092 行、`profile_service.py` 2355 行超过重要阈值，但本 task 分别净减 15 / 7 行（`--numstat` 25/40、1/8），不满足「本 task 仍净增」出 finding 条件；所审函数（`observation_is_current`、`_visible_observation`、`_latest_observation_geo_subquery`、`upgrade`）圈复杂度均 < 10；未发现范围外改动（diff 仅 TTL 退役、契约/文档同步与对应测试改造）。安全、契约·Breaking、性能·资源、健壮性·可观测、并发时序视角已逐项扫过：无新增外部输入拼接、无新查询缺 LIMIT/分页问题，迁移为 SQLite 正确的 batch 重建路径，未命中其他 finding。
- 总体判断：6 条 AC 的打勾在交付内容上均成立，核心读路径与迁移实现正确；仅遗留 1 处注释口径不一致（minor），无未解决 critical / important。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`OBSERVATION_TTL_SECONDS` 已不存在；`expires_at` 从 `EgressObservation`（`egress_observation.py:33-36`）、ORM（`models.py:95-100`）、`ProxyResponse`（`domain/models.py:149-159`）、repository 读写（`repository.py:1902-1916`、`2477-2483`）及 service 写入（`profile_service.py:2002-2005`、`2286-2289`）全部移除；两份 OpenAPI 各删 1 处观测字段、生成 `cbrowser_v1.d.ts` 删 1 处；全仓残留均为 auth/AutomationToken 字段或历史迁移 `0010`，无观测字段残留。
- AC-002：TICK-VALID，re_verified。`observation_is_current` 已无 `now` 参数（`egress_observation.py:38-54`），读路径 `_current_observation` / `_current_observations` 仅按 `observed_at desc, created_at desc, id desc` 取最新行、无任何时间条件（`repository.py:1944-1957`、`1979-2008`）；`test_t052_observation_repository.py` 以 4000 天前 `observed_at` 的 ok 行与新 `ProfileRepository` 实例重读同一库断言状态/国家/IP 不变。
- AC-003：TICK-VALID，re_verified。`observation_is_current` 对 ok/failed/pending 三类统一要求端点指纹与凭据版本匹配，仅 `ok` 另需出口 IP 与国家码（`egress_observation.py:46-54`），`_visible_observation` 对每行无差别应用（`repository.py:1919-1936`）；`test_t052_egress_observation.py` 参数化断言 failed/pending 在身份匹配时为 current、指纹或凭据失配时三类均不 current，`test_t052_observation_repository.py::test_endpoint_or_credential_change_invalidates_every_status` 覆盖仓库层。
- AC-004：TICK-VALID，re_verified。`_latest_observation_geo_subquery` 已删除 `expires_at IS NULL / > now` 时间过滤，改为全量按最新行排序后取 `rn=1, status=ok, country_code IS NOT NULL`（`repository.py:2215-2257`），并被 `list_proxies_page`（`:2276`、`:2294`）与 `proxy_country_ranges`（`:2381`）共用；`test_t076_collection_queries.py::test_proxy_country_ranges_match_collection_current_observation` 断言旧 ok 持续有效、新 pending 隐藏旧地理时两侧口径一致。
- AC-005：TICK-VALID，re_verified。迁移 0018 用 `op.batch_alter_table(..., recreate="always").drop_column("expires_at")`（`0018_remove_observation_expiry.py:31-33`），为 SQLite 删列正确路径，反射重建保留其余列与索引；`down_revision="e10400170001"` 接当前 head 0017，`downgrade` 抛 RuntimeError 拒绝；`test_t105_observation_expiry_retirement.py` 真实 Alembic 升级验证列消失、历史行 `latency_ms/country_code/city` 不变且仅一个 head。
- AC-006：TICK-VALID，re_verified。本次 diff 在 `profile_service.py` 仅删除两处成功写入的 `expires_at`、在 repository 删除写入字段与投影，probe-job 读模型、成员状态与 SSE `probe_job_progress` 路径未改；t094/t095 相关测试文件改动仅为移除 `expires_at` 字段依赖，进度/并发断言未动。

coverage = 6 / 6

verdict: PASS

## Round 2 (2026-11-23T14:55:00+08:00)

### 前轮 finding 复核

- t105_code_f001（minor，Round 1）：已消除。`src/backend/cbrowser/adapters/database/repository.py:2372-2379` 当前 docstring 为「aggregate over the same current rows the collection filter uses (`_latest_observation_geo_subquery`): the newest row per proxy, which must be an ok observation with a country. A newer non-ok row hides older geography in both paths, so no filter ever offers a dead option that resolves to zero rows.」。全文无 expired / TTL / still valid 措辞及时效解释，口径与 `_latest_observation_geo_subquery`（`repository.py:2215-2233`）新注释一致。以 diff 为准，确认真正修正而非撤回。

### 本轮新发现

- 0 条。本轮唯一交付变化是 f001 的 docstring 修正，未触及实现/迁移/契约/测试代码，不引入新问题。安全、正确性、契约·Breaking、性能·资源、架构·可维护性、健壮性·可观测、文档·规格 7 视角已独立复核扫过，无命中。

## 结论

- 前轮 finding 复核：t105_code_f001 已消除（docstring 改为无时效的「最新行」口径），无仍存在 / 修不彻底项。
- 本轮新发现：0 条
- 未进表的提示：`repository.py`（3092 行）、`profile_service.py`（2355 行）超过实现源码重要阈值 800 行，但本 task 分别净减 15 / 7 行（`--numstat` 25/40、1/8），不满足「本 task 仍净增」出 finding 条件；所审函数（`observation_is_current`、`_visible_observation`、`_latest_observation_geo_subquery`、`upgrade`）圈复杂度均 < 10；无范围外改动。
- 总体判断：f001 已消除，6 条 AC 在完整交付内容上均成立，核心读路径与迁移实现正确，无未解决 critical / important。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`OBSERVATION_TTL_SECONDS` 无代码残留；`expires_at` 从 `EgressObservation`（`egress_observation.py:18-36`）、ORM（`models.py:67-100`）、`ProxyResponse`（`domain/models.py:149-159`）、repository 读写（`repository.py:1898-1916`、`2455-2483`）及 service 写入（`profile_service.py:1992`、`2275`）全部移除；两份 OpenAPI 各删 1 处观测字段、生成 `cbrowser_v1.d.ts` 删 1 处；全仓 grep 剩余均为 auth/session/viewer_grants 字段、历史迁移 0001/0006 或 fixture，无观测字段残留。
- AC-002：TICK-VALID，re_verified。`observation_is_current` 无 `now` 参数、无时间条件（`egress_observation.py:38-54`）；读路径 `_current_observation` / `_current_observations` 仅按 `observed_at desc, created_at desc, id desc` 取最新行、无任何时间过滤（`repository.py:1938-1957`、`1959-2008`）；`test_t052_observation_repository.py` 以 4000 天前 ok 行与新建 Repository 实例重读同一库断言状态/国家/IP 不变。
- AC-003：TICK-VALID，re_verified。`observation_is_current` 对 ok/failed/pending 三类统一要求端点指纹与凭据版本匹配，仅 `ok` 另需出口 IP 与国家码（`egress_observation.py:38-54`），`_visible_observation` 对每行无差别应用（`repository.py:1919-1936`）；`test_t052_egress_observation.py` 参数化断言三类在身份匹配时为 current、指纹或凭据失配时三类均不 current。
- AC-004：TICK-VALID，re_verified。`_latest_observation_geo_subquery` 删除 `expires_at IS NULL / > now` 过滤，改为全量排序后取 `rn=1, status=ok, country_code IS NOT NULL`（`repository.py:2215-2257`），由 `list_proxies_page`（`:2259`）与 `proxy_country_ranges`（`:2372`）共用；`test_t076_collection_queries.py` 断言旧 ok 持续有效、新非 ok 隐藏旧地理时两侧口径一致。
- AC-005：TICK-VALID，re_verified。迁移 0018 用 `op.batch_alter_table(..., recreate="always").drop_column("expires_at")`（`0018_remove_observation_expiry.py:28-30`），SQLite 删列正确路径；`revision="b2c3d4e5f601"`、`down_revision="e10400170001"` 接当前 head 0017，`downgrade` 抛 RuntimeError 拒绝（`:33-34`）；`test_t105_observation_expiry_retirement.py` 真实 Alembic 升级验证列消失、历史行值不变、仅一个 head。
- AC-006：TICK-VALID，re_verified。本 task 在 `profile_service.py` 仅删除两处成功写入的 `expires_at`、在 repository 删除写入字段与投影，probe-job 读模型、成员状态与 SSE `probe_job_progress` 路径未改；t094/t095 相关测试改动仅为移除 `expires_at` 字段依赖，进度/并发断言未动。

coverage = 6 / 6

reviewed_scope: a35cbcf6290823ef

verdict: PASS
