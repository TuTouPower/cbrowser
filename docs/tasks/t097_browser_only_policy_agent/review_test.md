# Task review t097（reviewer_focus: 测试）

- task：`t097_browser_only_policy_agent`
- spec：`docs/tasks/t097_browser_only_policy_agent/task.md`
- diff_anchor：`4e007a694f1b5d3ada39ee29caa687df8198727f`
- target：`git diff 4e007a694f1b5d3ada39ee29caa687df8198727f`
- round：1
- reviewed_at：2026-11-21T13:13:58+08:00

reviewed_scope: f008c85d5d231a81

## Findings

### t097_test_f001 - 伪造 role 用例删除后，协议层 role=stream 拒绝无直接用例

- 严重度：minor
- 锚点：AC-003（身份判定拒绝伪造绑定）——非阻断：AC-003 另有覆盖，本条只是可再补一个 case
- 位置：`tests/unit/test_t082_policy_agent.py:93`（`test_identity_mismatch_is_rejected_for_every_op`，diff 从 forged_values 删除 `"role": "stream"`）
- 问题：`PolicyAgentIdentity.role` 已收敛为 `Literal["browser"]`（`src/backend/cbrowser/supervisor/policy_agent_protocol.py:52`，导出 schema 同步为 const），但没有任何测试直接断言 stream 角色在协议/身份模型层被拒；现存最近覆盖是适配器 ensure 路径拒绝（`tests/unit/test_t097_browser_only_policy_agent.py` 的 `test_stream_target_cannot_be_given_a_policy_agent`）与另一个模型 `NetworkPolicySpec` 的 validation（`tests/unit/test_network_policy.py:32`）。删除本身合法（伪造值在新协议下不可表示，无法再构造 mismatch 请求），其余 5 个伪造字段的拒绝断言保留，故不构成 AC 假覆盖。
- 建议：补一条直接用例，如以 `role="stream"` 构造 `PolicyAgentIdentity` 期望 ValidationError，或经 agent rig 发原始请求期望类型化拒绝。

## 结论

- 改测方向复核：无「迁就实现」的改测。逐项核对如下：
    - `tests/unit/test_a10_stream_egress.py` 整文件删除合法：9 例全部钉已废除的 Stream 规则渲染/安装契约；其中 Browser 断言与 `tests/unit/test_network_policy.py` 现有覆盖重复，`apply_policy` 失败封闭回退由未改动的 `tests/unit/test_network_policy_failure.py`（browser spec，3 例）覆盖。
    - `tests/unit/test_network_policy.py`：stream 渲染/媒体回包用例随 role 删除而删除；validation 改断言 stream 角色与 `udp_mux_port` 被拒（真实 pydantic 行为）；terminal 用例改测 Browser 直连 ACCEPT / 代理封闭 DROP 双族且新增无条件 ACCEPT 为空断言，是加强不是弱化。
    - `tests/unit/test_t026_network_policy_verify.py`：STREAM_SPEC 换为 proxy_enforced 的 Browser spec，canonical 样本按 Browser 渲染重写；verify/parse/canonicalize 机制与角色无关，DROP 终局与 round-trip 断言保留原强度。
    - `tests/unit/test_t026_supervisor_convergence.py` / `tests/unit/test_t082_supervisor_policy_convergence.py`：Stream 策略漂移/不可用场景改写为「Stream 策略状态不是收敛输入」（断言零变更且 ready），mid-flight 与跨 Profile 替换改由媒体漂移（conforms=False）触发——新触发是现存真实触发路径；删除的「Stream 预算耗尽失败」用例所测机制（替换预算）在 `test_t026_supervisor_convergence.py:906,1123` 对其它触发仍有覆盖。
    - `tests/unit/test_a9_stream_residue.py`：start 失败回收五例随机制删除，改为正向用例断言 Stream 启动不做任何策略动作且无 entrypoint 覆盖（mock 仅置于 Docker/内部 seam 边界，被测 `start_stream_container` 为真实生产实现）；core 残留契约三例保留。
    - `tests/unit/test_t051_docker_error_detail.py`：Stream residue 例改直构错误类型断言脱敏格式——其生产触发点已随策略面删除，属覆盖层级随契约收缩，剩余可观察行为（`docker_error_detail` 真实函数产出的 cause_type 与凭据脱敏）断言具体；core 侧残留处理仍由 test_a9 的 FakeAdapter 用例覆盖。policy 安装例补 `remember_profile_number("p1", 1)` 与生产前置一致（`docker_adapter.py:2986` 生产启动路径恒先记编号，core 亦然），非迁就。
    - `tests/unit/test_egress_plan_and_runner_sdk.py`：精确字典断言仅删 `udp_mux_port` 键，与 `egress_plan.py` spec 字典删键同步，断言仍为全等比较未弱化为子集。
    - `tests/unit/test_t051_supervisor_identity.py` / `tests/unit/test_t026_media_network_adapter.py`：fake 网络补 Internal 建模是跟随生产 create 新增 `internal=True` 参数的替身同步，非断言变更；后者另新增非 internal 不合规用例并断言 create 传 `internal=True`。
- 危险模式扫描：无恒真断言、无 skip/only、无注释掉断言、无阈值放宽、无条件跳过弱化。`tests/unit/test_network_policy.py:32,35` 新增的 `# type: ignore` 已调查放行：与该文件既有 46、170 行同一惯例，用于构造非法入参断言 ValidationError，不抑制任何运行时断言。删除断言/删测试均为上条所述契约删除且有等价或更高层覆盖。
- 新增测试可红验证（reviewer 独立执行）：把新/改测试放到基线（diff_anchor）代码归档上运行，5 例全红——`test_t097_browser_only_policy_agent.py` 三例（命名断言失败于旧散列名等）、`test_t026_media_network_adapter.py::test_routable_network_is_not_conforming`、`test_a9_stream_residue.py::test_stream_start_installs_no_policy_and_uses_image_entrypoint`；在当前代码上定向复跑共 203 例全绿（test_t097/test_t026_media/test_network_policy/test_t026_network_policy_verify/test_a9/test_egress_plan/test_t080/test_t082_policy_agent 66 例，test_t026/test_t082 收敛 + test_t051 两文件 90 例，test_t082_adapter_policy_agents/test_network_policy_failure/test_t051_supervisor_identity 47 例）。
- 全量门禁证据抽查（gate-t097-final2）：unit 失败集与 progress 所述基线逐条一致（FAILED 为 t063×2、t068×2、t095×1，ERROR 10 条全为 t063），integration 4 条 ERROR 与 frontend 1 条超时均为 progress 所述 setup/负载 flake 条目，未发现本 task 测试被悄悄改绿的迹象。
- 未知契约：task.md 中 SPIKE 已按用户裁定处置并登记 p159，AC-004/AC-005 已按裁定写处置注记并登记 p160/p161；按该契约注记核对，不判 TICK-VOID、不作 blocking。
- 本轮新发现：1 条（minor 1 条）
- 未进表的提示：`tests/unit/test_t082_supervisor_policy_convergence.py` 的 `_FakeAdapter` 仍保留已无生产调用方的 `stream_policy_spec` 死方法，属替身残留清理项，不影响断言可信。
- 总体判断：测试迁移均为「契约按 spec 变更」且逐项有归因，新增测试真实触达生产实现并经基线可红验证；仅 1 条 minor，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。定向复跑通过：`test_t097_browser_only_policy_agent.py` 断言每 Browser 恰一个 Agent、名称 `<prefix>-0001-policy-agent`、compose project/service 与 profile-number 标签，孤儿巡检删除 Stream Agent 并把旧形状 Browser Agent 替换为恰一个现行 Agent；未改动的 t082 套件覆盖 Supervisor 重启接管（`test_second_adapter_adopts_running_agent`）、停止拆除（`test_teardown_removes_profile_agents`）。
- AC-002：TICK-VALID，re_verified。`test_a9_stream_residue.py::test_stream_start_installs_no_policy_and_uses_image_entrypoint` 断言 Stream 启动无 gate/Agent/规则安装且无 entrypoint 覆盖（基线代码上可红）；t026/t082 收敛套件断言 Stream 策略状态不触发替换/隔离且观察为 ready，Gateway 替换只重挂接的既有用例保留并通过。
- AC-003：TICK-VALID，re_verified。`test_network_policy.py` 的 Browser 双族 terminal 断言（直连 ACCEPT、proxy_enforced DROP 且无无条件 ACCEPT）、`test_t026_network_policy_verify.py` 迁移后的 verify/漂移比较、t082 身份伪造拒绝（其余 5 字段）与 Browser 漂移失败封闭用例（t026 收敛套件）均复跑通过。
- AC-004：TICK-VALID，trust_prior。按 task.md 处置注记（用户裁定）打勾成立：真实 OrbStack 媒体与隔离矩阵延期本地补验（p160），reviewer 未独立复验真机部分；云端可做部分已复验——媒体 adapter 新增非 internal 网络不合规用例（基线可红）与 create `internal=True` 断言通过，Stream 无 Policy Agent 由 AC-002 证据支撑。
- AC-005：TICK-VALID，trust_prior。按 task.md 处置注记（用户裁定）打勾成立：真实 release 升级/回退延期本地补验（p161），reviewer 未独立复验；云端可做部分已复验——孤儿巡检与 ensure 路径的旧形状 Agent 收敛替换用例复跑通过且基线可红。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS

## Round 2 (2026-11-21T14:07:21+08:00)

reviewed_scope: 129a213d049dd250

### 前轮 finding 复核

- t097_test_f001（minor，协议层 role="stream" 拒绝无直接用例）：**已消除**。`tests/unit/test_t082_policy_agent.py:131` 新增 `test_stream_role_is_rejected_at_the_protocol_layer`，双层断言均为具体行为断言：以 `role="stream"` 构造 `PolicyAgentIdentity` 期望 `ValidationError`，以及原始 dict 载荷经 `PolicyAgentRequest.model_validate` 期望 `ValidationError`；生产侧 `src/backend/cbrowser/supervisor/policy_agent_protocol.py:53` 为 `role: Literal["browser"]`。reviewer 独立验证：该用例在当前代码上通过、在 diff_anchor 基线代码上真红（`Failed: DID NOT RAISE ValidationError`），非恒真/假绿。用例内的 `# type: ignore[arg-type]` 已调查放行：与轮 1 放行的同文件惯例一致，用于构造非法入参断言 ValidationError，不抑制任何运行时断言。
- 代码轴 f001 的测试面连带处置（本轴核对）：Stream 残留机制整链删除属实——`StreamContainerResidueError`、`cleanup_stream_residue`、`StreamResidue`、`_pending_stream_residue` 在 `src/` 与 `tests/` 中零引用（reviewer 全仓 grep 核实）。`tests/unit/test_a9_stream_residue.py` 三条 core 残留用例改写为一条 `test_replacement_failure_keeps_port_and_reports_failed`（`tests/unit/test_a9_stream_residue.py:185`），断言替换返回 False、端口 30000 保留、`cleanup_container_calls` 与 `transport_state == "failed"`，均为可观察行为；该用例在基线代码上亦通过，但其断言的正是新旧实现共同保留的可观察语义，被删断言只针对已删除的内部残留记账机制，不构成弱化。`tests/unit/test_t051_docker_error_detail.py` 的直构 `StreamContainerResidueError` 脱敏用例随类型本身删除而删除，同文件其余 docker 详情脱敏用例（如 `test_stream_start_failure_keeps_docker_detail_redacted`）保留，删除合法。

### 本轮复核证据

- 定向复跑（reviewer 独立执行）：`test_t082_policy_agent.py`（12 例）、`test_a9_stream_residue.py`（2 例）、`test_t051_docker_error_detail.py`（9 例）、`test_t097_browser_only_policy_agent.py`（3 例）共 26 例全绿。
- 门禁第三轮证据抽查（gate-t097-final3b）：unit 2408 passed、5 failed + 10 errors 与轮 1 基线集逐条一致（FAILED 为 t063×2、t068×2、t095×1，ERROR 10 条全为 t063）；较轮 2 的 2410 差 −2，与 a9 残留三改一（−2）、t051 删一（−1）、t082 增一（+1）的计数吻合（progress.md 逐项记录与日志一致）。integration 为 7 条 ERROR（test_normal_exit_replay×4、test_supervisor_start_capacity×1、test_supervisor_status_truth×2）、无 FAILED，与 progress 所述隔离 API 子进程就绪 setup flake 条目一致；其余套件 exit 0。
- 危险模式扫描（本轮 diff 新增行）：无 skip/only/xfail、无恒真断言、无注释掉断言、无阈值放宽；删测试两处均为上文所述机制/类型整链删除且有保留行为覆盖，非语法命中式删除。
- 改测方向复核：无「迁就实现」的改测。a9 改写断言的是保留的可观察语义，t051 删除随被测类型删除，t082 为纯新增覆盖。

## 结论

- 前轮 finding 复核：t097_test_f001 已消除（见上）；代码轴 f001 的测试面连带改动经核实为整链删除后的合法迁移，无弱化、无假绿。
- 改测方向复核：无
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：轮 1 唯一 minor 已真实修复并经基线可红验证，轮 2 测试面收缩均有契约归因且保留行为仍有断言，门禁计数与失败集抽查吻合；PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。定向复跑通过：`test_t097_browser_only_policy_agent.py` 3 例断言每 Browser 恰一个现行命名 Agent、孤儿巡检删除 Stream Agent 并替换旧形状 Browser Agent；t082 套件的接管/拆除用例本轮一并复跑通过。
- AC-002：TICK-VALID，re_verified。`test_a9_stream_residue.py` 两例复跑通过：Stream 启动无策略动作且用镜像自有入口、Stream-only 替换启动失败保端口且 transport 报 failed（断言强度与新契约一致）。
- AC-003：TICK-VALID，re_verified。新增协议层用例双断言复跑通过且基线可红，协议层 stream 角色拒绝已有直接覆盖；t082 身份伪造其余 5 字段拒绝用例保留并通过。
- AC-004：TICK-VALID，trust_prior。按 task.md 处置注记（用户裁定）打勾成立：真实 OrbStack 媒体与隔离矩阵延期本地补验（p160），reviewer 未独立复验真机部分；云端可做部分（声明式拓扑形状、Stream 无 Policy Agent）在轮 1 已复验，本轮无相关测试变更。
- AC-005：TICK-VALID，trust_prior。按 task.md 处置注记（用户裁定）打勾成立：真实 release 升级/回退延期本地补验（p161），reviewer 未独立复验；云端可做部分已复验——旧形状 Agent 收敛替换用例（`test_t097_browser_only_policy_agent.py`）本轮复跑通过。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS

## Round 3 (2026-11-21T14:13:54+08:00)

reviewed_scope: ab758f8a9865fd29

### 前轮 finding 复核

- 轮 2 无新 finding；轮 1 唯一 finding t097_test_f001（minor，协议层 role="stream" 拒绝无直接用例）已在轮 2 复核消除，本轮再确认仍消除：`tests/unit/test_t082_policy_agent.py:131` 的 `test_stream_role_is_rejected_at_the_protocol_layer` 仍在，且在本轮定向复跑中通过。

### 本轮复核证据

- 增量核实：相对轮 2，交付变更仅 `docs/tasks/t097_browser_only_policy_agent/task.md`「未知契约清单」中 SPIKE 处置句一处措辞——该文件第 72 行现为「SPIKE 处置（云端执行裁定，2026-11-21）：原待实测 spike 项『固定媒体拓扑在目标 OrbStack 上能否同时满足宿主回环 UDP 发布、Gateway 信令与 Stream 出站隔离』……」，处置条目内已无字面标记词，改称「原待实测 spike 项」。处置含义未动，逐项与轮 2 口径一致：云端无 Docker/OrbStack 不可执行、登记 p159 留待本地实测成功与拒绝矩阵、云端按声明式拓扑先行落地（per-Profile 媒体网络为 internal 受管网络、Stream 的 UDP mux 继续只发布宿主回环）、真机等价性由 p159 确认且不成立时按新 ADR 回退条件修订、云端代码与自动测试只断言声明式形状本身。同文件第 68 行的 UNVERIFIED 字样属规范模板说明文字，非未知契约条目，不作标记残留论。
- 测试面一致性：AC 文本与打勾状态与轮 2 一致（AC-001 至 AC-005 全为 `[x]`，AC-004/AC-005 处置注记与 p160/p161 登记未动），无代码/测试变更迹象；本轮 reviewed_scope 指纹更新为 ab758f8a9865fd29，与上述单处措辞变更对应。
- 定向复跑（reviewer 独立执行）：`test_t082_policy_agent.py`（12 例）、`test_a9_stream_residue.py`（2 例）、`test_t051_docker_error_detail.py`（9 例）、`test_t097_browser_only_policy_agent.py`（3 例）共 26 例全绿，与轮 2 定向复跑结果一致。
- 门禁证据抽查（gate-t097-final3b，本轮未重跑全量门禁）：unit 2408 passed、5 failed + 10 errors 与轮 1/轮 2 基线集逐条一致（FAILED 为 t063×2、t068×2、t095×1，ERROR 10 条全为 t063）；integration 224 passed、7 errors 为轮 2 已定性的隔离 API 子进程就绪 setup flake 条目；其余套件 exit 0。抽查结果与轮 2 完全一致，门禁证据仍适用于当前测试面。
- 危险模式扫描（本轮增量）：增量仅文档措辞，无测试文件变更；对相对 diff_anchor 的全量 diff 新增测试行再扫一遍，无 `.skip` / `.only` / xfail、无恒真断言、无注释掉断言、无阈值放宽命中。
- 改测方向复核：本轮无任何改测。

## 结论

- 前轮 finding 复核：轮 2 零新 finding；t097_test_f001 保持消除（见上）。
- 改测方向复核：无
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：轮 2 之后唯一交付变更为 SPIKE 处置句的措辞修改（去掉字面标记词、改称「原待实测 spike 项」），处置含义、AC 文本、代码与测试面均未动，定向复跑与门禁证据抽查与轮 2 一致；PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。定向复跑通过：`test_t097_browser_only_policy_agent.py` 3 例断言每 Browser 恰一个现行命名 Agent、孤儿巡检删除 Stream Agent 并替换旧形状 Browser Agent，本轮与 t082 套件一并复跑全绿；本轮措辞变更不涉及本条。
- AC-002：TICK-VALID，re_verified。`test_a9_stream_residue.py` 两例本轮复跑通过：Stream 启动无策略动作且用镜像自有入口、Stream-only 替换启动失败保端口且 transport 报 failed。
- AC-003：TICK-VALID，re_verified。`test_t082_policy_agent.py` 本轮 12 例复跑通过，含协议层 stream 角色拒绝双断言用例（第 131 行）与身份伪造其余字段拒绝用例。
- AC-004：TICK-VALID，trust_prior。按 task.md 处置注记（用户裁定）打勾成立：真实 OrbStack 媒体与隔离矩阵延期本地补验（p160），reviewer 未独立复验真机部分；云端可做部分在轮 1 已复验，本轮无相关测试变更，SPIKE 措辞变更不改变 p159/p160 的处置登记。
- AC-005：TICK-VALID，trust_prior。按 task.md 处置注记（用户裁定）打勾成立：真实 release 升级/回退延期本地补验（p161），reviewer 未独立复验；云端可做部分已复验——旧形状 Agent 收敛替换用例（`test_t097_browser_only_policy_agent.py`）本轮复跑通过。

coverage = 3 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS
