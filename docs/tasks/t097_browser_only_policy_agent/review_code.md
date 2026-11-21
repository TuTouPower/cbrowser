# Task review t097（reviewer_focus: 代码）

- task：`t097_browser_only_policy_agent`
- spec：`docs/tasks/t097_browser_only_policy_agent/task.md`
- diff_anchor：`4e007a694f1b5d3ada39ee29caa687df8198727f`
- target：`git diff 4e007a694f1b5d3ada39ee29caa687df8198727f`
- round：1
- reviewed_at：2026-11-21T13:13:09+08:00

reviewed_scope: f008c85d5d231a81

## Findings

### t097_code_f001 - Stream 残留（residue）机制的生产触发点已删除但整条消费链仍保留，成为死代码

- 严重度：minor
- 锚点：行为缺陷（死代码）+ 本 task 删除 `_reclaim_created_stream` 后，`StreamContainerResidueError` 在 `src/` 内再无任何 `raise` 点（已 grep 全仓核实），残留记录链永远不会被填充
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:197`（`StreamContainerResidueError`）、`src/backend/cbrowser/supervisor/docker_adapter.py:2533`（`cleanup_stream_residue`）、`src/backend/cbrowser/supervisor/core.py:307` 与 `src/backend/cbrowser/supervisor/core.py:1061-1140`（`_pending_stream_residue` 的读取/清理与 `except StreamContainerResidueError` 分支）
- 问题：`_pending_stream_residue` 是进程内字典，只由 `core.py:1140` 的 except 分支写入，而该异常在生产代码中已无产生者；`cleanup_stream_residue` 仅被该字典的消费分支调用。progress.md 称保留理由为「跨版本状态清理」，但进程内字典不跨进程/版本存续，该理由不成立。当前无可观测行为错误：Stream 启动失败改走 `start_stream_container` 的通用 `DockerSandboxError` 分支，`_replace_stream_only` 的 except 亦能接住，故仅评 minor。
- 建议：二选一并落字：要么整体删除 residue 类型、`cleanup_stream_residue` 与 core 的 pending 字典/except 分支（及其专属测试构造），要么在代码注释中写明保留的真实契约（如外部/测试直接构造该错误类型的兼容面）并给出后续清理 tid。

### t097_code_f002 - runtime_lifecycle spec 仍保留一行已废除的 Stream 规则集口径，与同文件 t097 新口径矛盾

- 严重度：minor
- 锚点：文档与实现不一致 + 同一 spec 内自相矛盾（该行紧邻本 task 改写的段落）
- 位置：`docs/specs/runtime_lifecycle.md:15`
- 问题：该行仍写「Stream 只允许实际 Gateway 端点、本实例 UDP mux 与显式白名单，并允许同机直连所需的已建立流量；私有/保留地址仍默认拒绝。独立 bridge 本身不构成隔离证明」，描述的是已被本 task 删除的 Stream 已安装规则集；而同文件本 task 新增段落已声明 Stream 无 Policy Agent、无已安装规则、隔离由 internal 媒体拓扑承担。读者按旧行会误以为 Stream 仍有规则面。
- 建议：把该行中 Stream 部分改写为拓扑口径（只经 internal 媒体网络与 Gateway 固定端点/本机媒体通道通信，出站由拓扑拒绝），或整行删除 Stream 子句（拓扑条目已在同文件媒体网络段落覆盖）。

## 结论

- 本轮新发现：2 条（均为 minor，无 critical / important）
- 未进表的提示：`src/backend/cbrowser/supervisor/docker_adapter.py` 物理行数 3003 行（远超实现源码 800 行 important 阈值），本 task 净增 7 行（+126/−119）；按文件过大降级规则只在此提示、不进 finding 表，该文件为存量巨型适配器，本 task 未使其职责进一步膨胀（净增主要为收敛逻辑与注释）。圈复杂度：本 task 新增/改写的函数（`_cleanup_orphan_policy_agents`、`ensure_policy_agent` 扫描段、`_agent_profile_number`）手算 CC 均 \<10，无提示项。范围外观察：无。
- 总体判断：实现与契约一致——Stream 侧 gate/Agent/规则安装/稳态校验整面删除干净（`start_stream_container` 无 gate 与 gated entrypoint、core 收敛与 readiness 只验 Browser 策略、协议与策略模型 role 收敛为 browser-only 且 schema 已同步导出）；媒体网络新建恒 `internal=True` 且 `inspect_media_network` 的 conforms 强制要求 Internal，存量可路由网络经既有漂移→Stream-only 重建收敛；Browser Agent 命名 `<prefix>-<NNNN>-policy-agent`、`<prefix>-profiles` 分组与 profile-number 标签落地，接管/孤儿清理仍以 deployment/profile/instance/config/目标容器全等身份判定，删除路径有 `_owns_deployment` 复核，相似名称与第二部署不会被误清。定向复跑测试 96 例全过（test_t097、test_network_policy、test_t026_media_network_adapter、test_egress_plan_and_runner_sdk 共 34 例；test_t082_supervisor_policy_convergence、test_t026_supervisor_convergence、test_t082_policy_agent、test_a9_stream_residue 共 62 例）。
- 系统性 follow-up：无（f001 的死代码清理属本 task 内 minor 处置，不另开 follow-up）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`policy_agent_labels` 注入 profile-number 与 compose 分组标签（container_spec.py:237），`_policy_agent_name` 按展示编号命名，test_t097 断言容器名/分组/service/编号标签且启动收敛后恰存一个现行 Agent，定向复跑通过。
- AC-002：TICK-VALID，re_verified。`start_stream_container` 已删除 gate 准备、gated entrypoint、role=stream 的 ensure 与规则安装（docker_adapter.py Stream 启动段），core `_converge_session` 与 readiness 删除 Stream 策略校验整段，Stream 信令注册/替换路径保留，相关收敛套件复跑通过。
- AC-003：TICK-VALID，re_verified。Browser 策略校验、漂移 fail-closed 与暂停隔离逻辑在 core 收敛中原样保留；`_policy_agent_identity` 对非 browser role 直接拒绝，`_agent_labels_match` 与 `_remove_policy_agent_container` 的身份/部署归属复核未弱化，test_t097 断言 Stream 目标拒绝建 Agent。
- AC-004：TICK-VALID，trust_prior。按用户裁定处置注记打勾：云端可做部分（媒体网络 `internal=True` 创建、inspect conforms 强制 Internal、失配走不合规收敛）已在代码层核对，但真机媒体与隔离矩阵无法在云端复验，依赖本地补验 p160 的后续证据。
- AC-005：TICK-VALID，trust_prior。按用户裁定处置注记打勾：旧形状收敛逻辑（孤儿扫描删 Stream Agent、ensure 替换旧名 Browser Agent）已在代码层核对且 test_t097 复跑通过，但真实 release 升级/回退无法在云端复验，依赖本地补验 p161 的后续证据。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS

## Round 2 (2026-11-21T14:07:50+08:00)

- task：`t097_browser_only_policy_agent`
- diff_anchor：`4e007a694f1b5d3ada39ee29caa687df8198727f`
- target：`git diff 4e007a694f1b5d3ada39ee29caa687df8198727f`
- round：2
- reviewed_at：2026-11-21T14:07:50+08:00

reviewed_scope: 129a213d049dd250

## Findings

本轮无新发现（0 条）。

## 结论

- 前轮 finding 复核：
    - t097_code_f001：已消除。以 diff 与 grep 为准（不采信处置表自述）：`StreamResidue` / `StreamContainerResidueError` 已从 `src/backend/cbrowser/supervisor/docker_adapter.py` 整段删除（连同 `_reclaim_created_stream` 之后的 `cleanup_stream_residue`），`start_stream_container` 的 except 分支只剩通用 `DockerSandboxError` / `DockerException` 脱敏重抛，注释明确失败容器由下一次启动按名清理（`core.py` 的 `_replace_stream_only` 在启动前确有 `cleanup_container_by_name` 调用，`src/backend/cbrowser/supervisor/core.py:1060`）；core 侧 import、`_pending_stream_residue` 字典、`_replace_stream_only` 的前置残留清理与 `except StreamContainerResidueError` 分支全部删除，失败走通用 except 置 transport failed 并返回 False（`src/backend/cbrowser/supervisor/core.py:1119-1131`）。全仓 grep `StreamContainerResidueError|cleanup_stream_residue|_pending_stream_residue|StreamResidue` 在 `src/` 内零命中（仅历史 task 文档与本报告前轮文字提及，非生产引用）。测试处置与处置表一致：`tests/unit/test_a9_stream_residue.py` 三条残留契约用例改写为一条通用启动失败用例（断言保端口、transport failed、按名清理），另有 Stream 启动无策略动作的正向用例；`tests/unit/test_t051_docker_error_detail.py` 直构残留错误脱敏用例已删除、import 同步清理。删除未引入悬空引用：定向复跑见下。
    - t097_code_f002：已消除。`docs/specs/runtime_lifecycle.md:15` 已改写为拓扑口径（「Stream 不安装任何地址规则，其可达面由拓扑决定：仅同一 internal 媒体网络上的 Gateway 与经共享 IPC 的对应 Browser……出站隔离不依赖已安装规则」），同文件第 14 行亦为 Browser-only Agent 口径，旧的 Gateway 端点/UDP mux/白名单规则集表述不复存在，文件内无自相矛盾。
- 本轮新发现：0 条。修复过程引入的新问题扫描：残留链删除后无未解析 import（core/docker_adapter 定向套件可正常收集与运行）；`_replace_stream_only` 失败语义未变（有界失败、保留端口分配）；安全/契约/性能/健壮性四视角复扫相对锚点的全量 diff（docker_adapter +126/−186 行、core +13/−117 行）未见新命中——删除路径的部署归属复核（`_remove_policy_agent_container` 与 `_scan_policy_agent_containers` 的 `_owns_deployment` 校验）未被本轮改动触及。
- 未进表的提示：`src/backend/cbrowser/supervisor/docker_adapter.py` 物理行数 2936 行、`src/backend/cbrowser/supervisor/core.py` 3541 行，均超实现源码 800 行阈值，但本 task 对两文件均为净减（分别 −60 行、−104 行），按文件过大降级规则只在此提示、不进 finding 表。圈复杂度：`_cleanup_orphan_policy_agents`（docker_adapter.py:821）手算 CC 约 12（≥10 提示档、未达 15 的 minor 档），分支均为身份校验与形状判定、无嵌套行为分叉，本轮未改动该函数，仅作提示。范围外观察：无。
- 总体判断：轮 1 两条 minor 均已按处置整链/整行消除且经独立复跑验证，当前 diff 无未解决 critical / important，本轮 PASS。门禁第三轮证据（gate-t097-final3b）与 progress.md 记录一致：unit 2408 passed、失败为既有云端基线集，integration errors 为子进程就绪 flake 且单跑通过；本轮 reviewer 定向复跑 145 例全绿（test_a9_stream_residue、test_t051_docker_error_detail、test_t082_policy_agent、test_t097_browser_only_policy_agent、test_t082_supervisor_policy_convergence、test_t026_supervisor_convergence 共 73 例；test_network_policy、test_t026_media_network_adapter、test_egress_plan_and_runner_sdk、test_t051_supervisor_identity、test_t026_network_policy_verify 共 72 例）。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`policy_agent_labels` 注入 profile-number 与 compose 分组标签（container_spec.py），`_policy_agent_name` 按展示编号命名，孤儿扫描对旧形状 Browser Agent 经 ensure 路径替换为现行形状；test_t097 三例（命名/分组标签、Stream 目标拒绝、启动收敛删 Stream Agent 并替换旧形状）本轮定向复跑通过。
- AC-002：TICK-VALID，re_verified。`start_stream_container` 无 gate 准备、gated entrypoint、role=stream 的 ensure 与规则安装，创建即启动终点；core 收敛与 readiness 只验 Browser 策略；test_a9 正向用例断言无策略动作且用镜像自有入口、改写后的通用失败用例断言替换失败保端口并报 failed，本轮复跑通过。
- AC-003：TICK-VALID，re_verified。Browser 策略校验、漂移 fail-closed 与暂停隔离逻辑保留；`_policy_agent_identity` 对非 browser role 直接拒绝，`_agent_labels_match` 与 `_remove_policy_agent_container` 的身份/部署归属复核未弱化，残留链删除未触及这些路径，相关套件复跑通过。
- AC-004：TICK-VALID，trust_prior。按用户裁定处置注记打勾：云端可做部分（媒体网络 `internal=True` 创建、inspect conforms 强制 Internal、失配走不合规收敛）已在代码层核对且 test_t026_media_network_adapter 本轮复跑通过，但真机媒体与隔离矩阵无法在云端复验，依赖本地补验 p160 的后续证据。
- AC-005：TICK-VALID，trust_prior。按用户裁定处置注记打勾：旧形状收敛逻辑（孤儿扫描删 Stream Agent、ensure 替换旧名 Browser Agent）已在代码层核对且 test_t097 本轮复跑通过，但真实 release 升级/回退无法在云端复验，依赖本地补验 p161 的后续证据。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS

## Round 3 (2026-11-21T14:14:13+08:00)

- task：`t097_browser_only_policy_agent`
- diff_anchor：`4e007a694f1b5d3ada39ee29caa687df8198727f`
- target：`git diff 4e007a694f1b5d3ada39ee29caa687df8198727f`
- round：3
- reviewed_at：2026-11-21T14:14:13+08:00

reviewed_scope: ab758f8a9865fd29

## Findings

本轮无新发现（0 条）。

## 结论

- 前轮 finding 复核：t097_code_f001、t097_code_f002 均已消除（轮 2 已以 diff 与 grep 复核整链/整行删除与改写；本轮代码与文档交付未再变动该两处——见下增量核实，结论沿用且仍成立）。
- 轮 2 后增量核实：相对锚点的 diff 中，`src/backend/cbrowser/supervisor/docker_adapter.py`（+126/−186）与 `src/backend/cbrowser/supervisor/core.py`（+13/−117）的 numstat 与轮 2 报告记录逐项一致，代码/测试文件内容未变；契约区 AC-001 至 AC-005 正文与轮 2 一致，仅打勾与 AC-004/AC-005 处置注记（轮 2 已复核）。唯一交付变更为 `docs/tasks/t097_browser_only_policy_agent/task.md:72`「未知契约清单」SPIKE 处置句的措辞：处置条目本身已无字面 `UNVERIFIED-SPIKE` 标记词（改述为「原待实测 spike 项」），全文仅第 68 行规范注释块保留模板规范用语（门禁必留文字，非清单条目）；该修改不改变处置含义，不构成未经确认的契约变更（drift 警告所列差异仍只有打勾与处置注记，AC 正文零改动）。
- SPIKE 处置表述一致性复核：task.md:72 与三处记载逐项对齐——progress.md 实施笔记首条（spike 登记 p159 留本地实测、云端按契约形状落地声明式拓扑、真机等价性由 p159 确认）与收尾报告遗留项（p159/p160/p161）；ADR 041（`docs/blueprint/decisions/20261121_stream_topology_isolation.md`）「验证与回退」段（p159 隔离最小拓扑 spike 实测回环发布可达与回包、信令与拒绝矩阵、IPv6 双栈；不成立时回退条件为改回可路由 bridge 的同时以等价声明式手段恢复 Stream 出站拒绝、不得恢复 Stream Policy Agent）；p159 文件（`docs/pending/p159_t097_media_topology_orbstack_spike.md`，status todo，内容为目标 OrbStack 最小拓扑实测成功与拒绝矩阵、不成立按 ADR 回退条件修订拓扑）。四处对「登记 p159 本地实测、云端按声明式拓扑先行（per-Profile internal 媒体网络无 NAT 出站、Gateway 固定端点信令、Stream UDP mux 只发布宿主回环）、链路本地媒体回包的真机等价性待 p159 确认、回退条件」的表述一致，无矛盾。
- 本轮新发现：0 条。本轮变更仅为文档措辞，安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测各视角无新命中面；本轮 reviewer 定向复跑 18 例全绿（test_t097_browser_only_policy_agent、test_t026_media_network_adapter、test_a9_stream_residue）。
- 未进表的提示：`src/backend/cbrowser/supervisor/docker_adapter.py` 物理行数 2936 行、`src/backend/cbrowser/supervisor/core.py` 3541 行，与轮 2 相同（本轮未触及两文件），按文件过大降级规则只在此提示、不进 finding 表。圈复杂度：本轮无代码变更，无新提示项。范围外观察：无。
- 总体判断：轮 2 后唯一变更为 SPIKE 处置句措辞修正，处置含义与 progress.md、ADR 041、p159 四处一致，代码/测试/AC 文本零变更，前轮 finding 消除状态不变，当前无未解决 critical / important，本轮 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。代码层与轮 2 一致（numstat 逐项相同）：`policy_agent_labels` 注入 profile-number 与 compose 分组标签、`_policy_agent_name` 按展示编号命名；test_t097 本轮定向复跑通过。
- AC-002：TICK-VALID，re_verified。`start_stream_container` 无 gate、gated entrypoint、role=stream 的 ensure 与规则安装，残留链已整链删除；test_a9_stream_residue 本轮定向复跑通过。
- AC-003：TICK-VALID，re_verified。Browser 策略校验、漂移 fail-closed 与身份/部署归属复核路径本轮未被任何变更触及（代码 numstat 与轮 2 一致），轮 2 复跑结论成立。
- AC-004：TICK-VALID，trust_prior。按用户裁定处置注记打勾：云端可做部分（媒体网络 `internal=True` 创建、inspect conforms 强制 Internal、失配走不合规收敛）代码未变，test_t026_media_network_adapter 本轮复跑通过，但真机媒体与隔离矩阵无法在云端复验，依赖本地补验 p160 的后续证据。
- AC-005：TICK-VALID，trust_prior。按用户裁定处置注记打勾：旧形状收敛逻辑（孤儿扫描删 Stream Agent、ensure 替换旧名 Browser Agent）代码未变且 test_t097 本轮复跑通过，但真实 release 升级/回退无法在云端复验，依赖本地补验 p161 的后续证据。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS
