---
pid: "p168"
slug: "proxy_probe_results_expire_silently"
status: "closed"
resolution: "transferred"
reason: "已核实根因与范围并转交该 task"
fix_ref: "t105"
---
# p168 代理测速结果 24 小时后静默失效：用户感知为「重启后测速结果没了」

- 来源：用户 2026-11-23 截图反馈「似乎重启一下这些测速结果就没了」。截图（代理列表 88 条）状态列几乎全是「未测速」，仅 4 条显示「经代理无响应」。bug-to-pending 分析登记，未在本次分析修改生产代码。
- 现象：
    - 现场库（`cbrowser-db` 命名卷，`/data/db/cbrowser.db`）中 88 个代理的**最新观测行**为 84 条 `ok` + 4 条 `failed`。84 条 `ok` 中 77 条 `expires_at` 已过（最近一次批量测速为 2026-11-20T15:31Z，24h TTL 在 2026-11-21T15:31Z 到期；另 7 条 2026-11-22T05:14Z 的观测到 2026-11-23T05:14Z 才到期）。4 条 `failed`（`echo_unreachable`，无 `expires_at`）无过期时间，始终可见——与截图「4 条经代理无响应、其余未测速」逐行吻合。
    - 用生产 `ProfileRepository` 对库快照做受控时间复现：同一行「马来西亚标准 IEPL 专线 1」在 2026-11-20T16:00Z 返回 `status=ok, latency_ms=619`，在 2026-11-23T03:00Z 返回 `status=unknown, latency_ms=None`（UI 即「未测速」）；同一时刻 `failed` 行仍返回 `status=failed, error_code=echo_unreachable`。
    - **重启本身不丢数据**：全仓无启动期 `DELETE FROM proxy_egress_observations`，DB 在命名卷上；`app.py:384` 启动只 `resume_pending_probe_jobs()` 重启在途作业，不清空观测。用户把「TTL 到期」归因为「重启导致」，因重启与该状态变化相隔约 49 分钟且用户此前未刷新观察。
- 影响：
    - 代理列表状态列（`src/frontend/src/features/proxies/ProxyTable.tsx:135-162`）、卡片视图（`ProxyListPage.tsx:89-120`）、编辑弹窗（`ProxyFormDialog.tsx:452-491`）、会话详情（`SessionDetailsPanel.tsx:156-165`）同步退化为「未测速」；延迟毫秒数、出口 IP、国家/城市全部消失。
    - 国家/城市筛选范围同步塌陷：`repository.py:2221-2258` 的 `_latest_observation_geo_subquery` 排除过期 `ok` 行，`GET /api/v1/proxies/countries` 的取值范围随之减少；用户刷新/重启后不仅测速结果没了，筛选选项也少。
    - 现有实现**不会自动重测**：`docs/specs/proxy_management.md:54` 明确要求「观测过期时旧观测立即失效……并自动重新探测」，但全仓只在创建/端点变更时 `_schedule_probe`（`profile_service.py:1925-1926, 2338-2345`），启动路径只有作业恢复（`app.py:384`）。所以过期后代理长期停在「未测速」，直到用户手动触发测速。
    - UI 无法区分「从未测速」与「结果已过期」：两者都映射为 `unknown` → 「未测速」（`i18n.tsx:1072`、`ProxyTable.tsx:158-160`），用户无法判断是没测过还是旧结果失效。
- 根因（可验证机制与分类）：**产品缺陷 / 规格未落地 + UX 语义缺失**，非环境、非配置、非纯测试假绿。
    1. `OBSERVATION_TTL_SECONDS = 24 * 3600`（`src/backend/cbrowser/domain/egress_observation.py:15`）是明确设计决定（ADR 029、`docs/blueprint/domain.md:13,81`），本身不是 bug；但把「测速延迟」与「Geo 观测新鲜度」绑在同一 24h TTL 上，且过期后无自动重测、无过期提示，导致用户已获得的测速结果在一天后无声消失。
    2. 失效链：`observation_is_current`（`egress_observation.py:51-60`）判 `status != ok` / `expires_at <= now` 为 false → `_visible_observation`（`repository.py:1922-1941`）对过期 `ok` 返回 None → `_to_domain_proxy`（`repository.py:1884`）回落 `observation_status="unknown"` → 前端 `ProxyTable.tsx:158-160` 显示「未测速」。
    3. `_current_observations`（`repository.py:1964-2014`）按 `observed_at desc` 取每代理最新一行；`failed` 行 `expires_at=None` 且 `_visible_observation` 对 `status != ok` 直接放行，因此失败结果永久保留，进一步强化「只有测速成功结果消失」的错觉。
    4. 规格-实现缺口：`docs/specs/proxy_management.md:54` 要求过期自动重探，`docs/blueprint/domain.md:81` 只要求失效显示未测速（未提重探），两文档口径不一致；代码无任何过期重探入口。
    - 已确认同类位点（同一机制，合并进同一修复范围）：`ProxyTable.tsx`、`ProxyListPage.tsx` 卡片视图、`ProxyFormDialog.tsx`、`SessionDetailsPanel.tsx`、`repository.py:_latest_observation_geo_subquery`、`GET /api/v1/proxies/countries` 范围聚合。
    - 未确认残余（单列，不计入已确认范围）：`failed` 观测无 TTL、永久可见，数天前的 `echo_unreachable` 会一直显示；规格未规定失败是否也该过期，需产品裁决。
- 测试缺口：
    1. `tests/unit/test_t052_observation_repository.py:70-87` 把「过期 ok → unknown」作为 AC-007 预期钉死；该断言成立但**只覆盖了隐藏行为**，没有任何测试覆盖规格要求的「过期后自动重探」或「过期态与未测速态区分」，因此当前症状全绿。`test_t095_probe_job_progress.py:106-131` 只断言历史行保留和 `expires_at` 字段存在，不驱动时间跨越 TTL。
    2. 前端 `src/frontend/src/features/proxies/ProxyListPage.test.tsx` / `ProxyTable` 相关用例没有「观测过期后重挂/刷新」的断言，也没有国家/城市筛选范围随过期塌陷的断言。
    3. 修复后需补：后端在过期边界上断言「自动重探被提交（若按 spec 修复）」或「过期态在契约中与未测速可区分」；集成层断言 `/api/v1/proxies/collection` 与 `/countries` 在过期前后的一致性；前端断言状态列/卡片/弹窗/会话详情对过期态的文案与刷新后保持，并覆盖筛选范围同步。
- 线索：
    - `.scratch/repro_probe_result_after_restart/repro.py`（生产 `ProfileRepository` + DB 快照 + 注入冻结时间，直接输出 `ok→unknown`、`failed` 不变）；库快照 `.scratch/repro_probe_result_after_restart/cbrowser.db`；运行命令 `.venv/bin/python .scratch/repro_probe_result_after_restart/repro.py`。
    - 现场证据：`docker run --rm -v cbrowser-db:/db python:3.12-alpine python3 -c "..."` 查 `proxy_egress_observations` 最新行与 `expires_at`；截图对应 21065–21087 端口代理逐行状态与 DB 完全吻合。
- 处理：t105；resolution=transferred；reason=已核实根因与范围并转交该 task
