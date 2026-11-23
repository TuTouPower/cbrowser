# Task spec

## 背景

用户 2026-11-23 反馈代理列表「重启后测速结果没了」。核实结论：结果未因重启从 SQLite 丢失，而是 24h TTL 把整条观测快照作废，`observation_status` 回落 `unknown` → UI「未测速」；现场 84 条最新 `ok` 中 77 条已过期，4 条 `failed` 因无 TTL 永久可见，与截图吻合。进一步核实：`expires_at = datetime.now() + OBSERVATION_TTL_SECONDS(86400)` 完全是 API 自己填的写死常量（ADR 029 的产品约定），不是探测返回的数据；且 `ok` 有时效、`failed` 无时效，同一个观测元组存在两套规则。用户裁决：取消 TTL，观测快照整条永久有效，只在端点/凭据变化时失效并重测。按铁律直接删除整个时效维度，不新增任何调度/巡检机制。

## 契约区

### 范围

- 彻底删除 `OBSERVATION_TTL_SECONDS` 与 `expires_at`：领域值对象、ORM 模型、API DTO、OpenAPI 契约、前端生成类型与手写类型中该字段及常量全部消失。
- 统一「当前观测」判定：每代理取最新一行，且端点指纹与凭据版本匹配当前端点；`ok` 另需 `egress_ip` 与 `country_code`。不再有任何时间条件。`ok` / `failed` / `pending` 三类快照统一适用指纹与凭据版本规则。
- 数据库迁移 0018 删除 `proxy_egress_observations.expires_at` 列，保留其余历史行；只进不退。
- 国家/城市筛选范围（`_latest_observation_geo_subquery` 与 `/proxies/countries`）与列表展示取同一口径，删除时间过滤。
- 端点/凭据变化既有链路（pending → 探测 → 新快照 → 新快照成为当前）保持不变并被回归断言。
- 测试矩阵改造：删除 TTL 跨越相关断言，新增「任意时间点快照持续有效」与「端点变化失效」断言；前端覆盖列表/卡片/编辑弹窗/会话详情与刷新重挂。
- spec / blueprint / 新 ADR 同步删除 TTL 口径，记录取消决定。

### 非范围

- 不新增后台巡检、唤醒队列、周期重测或任何调度子系统（上一版方案整体作废）。
- 不拆分观测实体：`egress_ip` / 国家 / 城市 / `latency_ms` 属于同一快照元组，同生共死（用户明确裁决）。
- 不保留 `expires_at` 兼容字段、默认值或「保留列但不使用」的过渡形态（零兼容性负担）。
- 不改手动单条/批量测速入口与 t094/t095 的 SSE 进度语义。
- 不做 schema 反向迁移或 downgrade（沿用只进不退）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：`OBSERVATION_TTL_SECONDS` 常量与 `expires_at` 字段从 `domain/egress_observation.py`、`domain/models.py`、`adapters/database/models.py`、`adapters/database/repository.py`、迁移 0018 之后的 ORM/API 路径、`schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 及前端手写类型中全部移除；全仓代码（历史迁移文件除外）grep 无残留。
- [x] AC-002：任意一条成功观测写入后，在任意时间点（含注入时钟跨越原 24h 边界、API 进程重启后）仍是该代理当前观测；列表状态列、卡片视图、编辑弹窗只读观测区、会话详情持续展示同一 `latency_ms` 与国家/城市，直到端点/凭据变化或被新观测覆盖。
- [x] AC-003：端点或凭据变化后，最新快照因指纹/凭据版本失配而失效，触发既有 pending → 探测 → 新快照流程；新快照成为当前观测，旧观测仅留在历史中且不再展示。`ok` / `failed` / `pending` 三类快照统一适用该失效规则，不存在某一类永久可见或永久失效。
- [x] AC-004：`GET /api/v1/proxies/collection` 与 `GET /api/v1/proxies/countries` 均不按时间过滤观测；列表行展示与筛选范围的当前观测口径一致，在任意时间点返回同一代理的同一组国家/城市与延迟值。
- [x] AC-005：迁移 0018 在含历史观测的现有库上删除 `expires_at` 列后，其余观测历史行数与字段值不变，应用启动与读取正常；downgrade 仍按只进不退拒绝。
- [x] AC-006：手动单条/批量测速、服务端作业读模型与 SSE `probe_job_progress` 语义不变，t094/t095 相关测试回归通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试：AC-001 用全仓 grep 与契约文件比对；AC-002/003/004 用注入时钟、内存/SQLite 测试库与仓库读路径断言；AC-005 用临时库执行迁移前后列与行数比对；AC-006 为既有测试回归。AC-002 中「进程重启后」通过新建 Repository/Service 实例对同一库重读验证。

## 上下文区

- 关联 spec：docs/specs/proxy_management.md
- 来源：p168（2026-11-23 核实：77/84 条 `ok` 观测过期、4 条 `failed` 永久可见；`expires_at` 为 API 自填写死常量而非探测数据；用户裁决取消 TTL、保留同一快照元组）

### 有意不测

- 多 API 实例并发读写：单机单人部署只有一个 SQLite 写者，不在本 task 边界。
- 出口 IP/地理漂移的自动追踪：取消 TTL 后按设计不再随时间自动刷新，只有端点/凭据变化或手动测速才重测；不为此新增探测机制。

### 测试策略

- 后端单元：删除 `test_t052_egress_observation.py` / `test_t052_observation_repository.py` 中 TTL 过期断言，改为「跨任意时间保持有效」与「端点/凭据变化失效且三类状态一致」断言。
- 集成：`test_t076_collection_api.py` / `test_t076_collection_queries.py` / `test_t095_probe_job_progress.py` 去掉 `expires_at` 字段依赖，断言 collection 与 countries 口径一致。
- 迁移：临时库跑至迁移 0017 后灌入样本观测，执行 0018，断言列消失且行数与值不变。
- 前端：组件测试覆盖列表/卡片/编辑弹窗/会话详情对持久快照的展示、刷新重挂无本地状态残留，以及生成类型中无 `expires_at`。
- 契约：OpenAPI 与生成类型比对门禁确认字段删除已同步。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无

### 风险与回退

- 风险：删除列属不可逆破坏性迁移，旧版本应用读新库会失败；`ok` / `failed` 时效规则统一后，长期失败的代理会一直显示旧错误码直到端点变化或手动测速。
- 回退：按只进不退约定，用 release 回滚 + 数据目录重建，不写反向迁移；不新增运行时开关保留旧语义。

### 依赖与约束

- 破坏性变更，零兼容性负担：不保留 `expires_at` 列、字段或常量，不做双读双写。
- 迁移 revision 接当前 head 0018（或实际下一号），沿用只进不退与 downgrade 拒绝约定。
- 契约文件 `schemas/openapi/cbrowser_v1.json` / `cbrowser_internal.json` 与前端生成类型必须同批更新，避免消费方按过期契约开发。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：出口观测定义删除 TTL 与过期失效规则，改为快照永久有效 + 端点/凭据版本失效。
- `docs/blueprint/architecture.md`：读模型口径改为无时间条件，删除过期隐藏链路。
- `docs/blueprint/frontend.md`：状态列与筛选范围展示口径同步。
- `docs/specs/proxy_management.md`：§7 删除 TTL 24h 描述，front matter `tasks` 登记 t105。
- `docs/blueprint/decisions/`：新增 ADR 记录取消 TTL、快照同生共死的决定与理由。
