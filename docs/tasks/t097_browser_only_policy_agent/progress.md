---
tid: "t097"
slug: "browser_only_policy_agent"
title: "推流网络依职责隔离与浏览器 Policy Agent 归组"
status: "done"
branch: "t097_browser_only_policy_agent"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "4e007a694f1b5d3ada39ee29caa687df8198727f"
spec_source_sha: "4e007a694f1b5d3ada39ee29caa687df8198727f"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 契约处置（2026-11-21 云端执行）：UNVERIFIED-SPIKE 改写为处置结论（spike 登记 p159 留本地实测；云端按契约形状落地声明式拓扑——per-Profile 媒体网络 internal 化，Stream UDP mux 仍只发布宿主回环，真机等价性由 p159 确认）；AC-004/AC-005 按用户裁定在 task.md 契约区写处置注记后打勾，真实验证分别登记 p160/p161 留待本地。
- 拓扑选定依据（源码实测）：媒体网络现为 per-Profile bridge＋固定端点计划（plan labels/IPAM 一致性巡检、漂移走 rebuild 收敛）；Browser 与 Stream 均接入该网络、Gateway 以固定端点接入。internal 化后同网信令与媒体通道不变，出站由网络本身无 NAT 保证；inspect_media_network 的 conforms 增加 Internal 要求，存量非 internal 网络经既有漂移→Stream-only 替换（rebuild_network）路径一次性收敛。
- Stream 去策略落点：docker_adapter.start_stream_container 删除 gate 准备、gated entrypoint（改用 stream 镜像自有 ENTRYPOINT）、role=stream 的 ensure_policy_agent 与 \_install_network_policy、失败路径的 Agent 回收；core.\_converge_session 删除 Stream 策略校验/漂移替换整段（保留媒体接入与 Gateway 注册校验）；core.note_policy_agent_event 只处理 browser；docker_adapter.stream_policy_spec 删除；PolicyAgentIdentity 与 NetworkPolicySpec 的 role 收敛为 browser-only（udp_mux_port 字段随之删除），协议 schema 经 scripts/export_policy_agent_protocol.py 重新导出；stream_volumes 删除 gate 挂载。
- Browser Agent 改名落点：container_spec.policy_agent_labels 增加 profile-number 标签与 sandbox_compose_labels(prefix, "policy-agent", number)（project 沿用 `<prefix>-profiles`、service 为 `<NNNN>-policy-agent`）；docker_adapter.\_policy_agent_name 改为 `<prefix>-<NNNN>-policy-agent`（编号经 \_require_profile_number 解析，与 browser/stream 容器同款命名）。
- 存量收敛落点：\_cleanup_orphan_policy_agents 对 target-role=stream 的 Agent 一律按完整身份校验后删除（目标存活与否无关，Stream Agent 已废除）；ensure_policy_agent 在按名查找之外，先扫描绑定同一 target 的 Agent——标签全等且现行命名者接管、旧形状（旧名/缺分组标签）者先删除再按新形状创建，保证升级后每个 Browser 至多一个现行 Agent。
- 实施完成（2026-11-21）：上述落点全部落地；另删除 start_stream_container 中已无触发点的创建后回收接线（\_reclaim_created_stream）——其服务的失败模式（策略安装/端点解析/gate 就绪）随策略面一并消失。NetworkPolicySpec 删除 udp_mux_port 字段、egress_plan 的 spec 字典同步删键；协议 schema 已用 scripts/export_policy_agent_protocol.py 重新导出（role 为 const browser）。（注：cleanup_stream_residue 与 core 残留记录最初保留并记为「跨版本状态清理」，审阅轮 1 指出该理由不成立——残留字典仅进程内、唯一写入点是捕获该错误类型的 except 分支而生产已无抛出点——已整链删除，见 Review 处置 t097_code_f001。）
- 测试迁移（契约变更、非凑实现）：test_network_policy 的 stream 渲染/媒体回包用例随 stream 角色删除而删除、validation 改断言 stream 角色与 udp_mux_port 字段被拒、output terminal 改测 Browser 直连/代理封闭双族；test_t026/test_t082 收敛套件的 Stream 策略漂移/不可用场景改写为「Stream 策略状态不是收敛输入」、mid-flight 与跨 Profile 用例改由媒体漂移触发、readiness 不可验触发改为 Browser 缺失、Agent 事件定点修复只剩 Browser；test_a9 的 start 失败回收五例随机制删除，改为一条「Stream 启动不做任何策略动作且用镜像自有入口」的正向用例（core 残留契约用例在审阅轮 1 后随残留链整链删除而改写为通用失败保端口用例，见 Review 处置）；test_egress_plan 的 spec 精确字典断言删 udp_mux_port 键；test_t082_policy_agent 的身份伪造集删 role 字段（协议层已不可表示）；test_t026_media_network_adapter 的 fake 网络补 Internal 建模并断言 create 传 internal=True。新增 tests/unit/test_t097_browser_only_policy_agent.py（命名/分组标签、Stream 目标拒绝建 Agent、启动收敛删 Stream Agent 并替换旧形状 Browser Agent）与 media adapter 的非 internal 不合规用例。
- 文档闭环：specs（runtime_lifecycle/webrtc_remote_display/browser_isolation/release_deployment）口径更新并登记 t097；blueprint architecture/supervisor/testing 同步；新增 ADR 041（docs/blueprint/decisions/20261121_stream_topology_isolation.md，引用 ADR 031/038/039/040 与 t083，含 spike 不成立时的回退条件）。
- 门禁第一轮（证据 gate-t097-final1）处置：新 worktree 未装前端依赖导致 protocol_drift_check/frontend_test/frontend_build exit 127、design 两套件 exit 1、test_a16 协议漂移用例失败——环境准备问题，已 npm ci 后重跑（非代码问题）。unit 19 failed + 14 errors 中：5 failed + 10 errors 为既有云端基线（t063/t068/t095，与 t098 基线集一致）；t027 回滚就绪 1 条单跑通过（与 t098 final4 同款负载 flake）。其余为本 task 契约迁移遗漏，逐项处置：tests/unit/test_a10_stream_egress.py 整文件删除（9 例全部钉已废除的 Stream 规则渲染/安装契约，其中 2 例 Browser 断言与 test_network_policy 现有覆盖重复）；test_t026_network_policy_verify 的 STREAM_SPEC 改为 proxy_enforced 的 Browser spec、canonical 样本按 Browser 渲染重写；test_t051_supervisor_identity 的 fake networks.create 补 internal 建模；test_t080_storage_layout 的 stream_volumes 调用删 gate 参数；test_t051_docker_error_detail 两例——策略安装例补 remember_profile_number（生产安装路径恒已知展示编号）、Stream residue 例先改直构错误类型断言脱敏格式、后在审阅轮 1 随残留链整链删除一并删除（见 Review 处置 t097_code_f001）。
- 顺带的生产健壮性修复（门禁暴露）：Agent 命名/标签所需的展示编号此前只查 Supervisor 记忆映射，接管存量 Browser 时映射未学习会直接失败——docker_adapter 新增 \_agent_profile_number，映射缺失时回退读目标容器自身的 com.cbrowser.profile-number 标签，ensure/create/孤儿收敛三处统一经此解析。
- 门禁第二轮（证据 gate-t097-final2）：protocol_drift_check / requirements_check / design_lint / design_check / contract / frontend_build 全部 exit 0。unit 2410 passed，5 failed + 10 errors 与云端基线集逐条一致（t063×2、t068×2、t095×1 failed 与 t063/t068 的 10 errors）。integration 227 passed、4 errors（test_normal_exit_replay×3 + test_supervisor_start_capacity×1，均为隔离 API 子进程 10 秒内未就绪的 setup 错误），两文件单跑 5/5 通过，定性负载 flake（与 t098 门禁同类）。frontend_test 唯一失败为 ProfileForm 时区/语言对齐用例 6.5s 超时（本 task 未动前端），单跑该文件 16/16 通过，定性负载 flake。
- 审阅轮 1 两轴 PASS（code 2 minor、test 1 minor）后按处置整链删除 Stream 残留机制并补协议层用例（见 Review 处置），撤回全部 AC 打勾后跑门禁第三轮（证据 gate-t097-final3b；首跑 final3 中途被运行时 SIGTERM 杀死、unit 无结果，改 setsid 脱离会话重跑）：protocol_drift_check / requirements_check / design_lint / design_check / contract / frontend_build / frontend_test 全部 exit 0（frontend_test 本轮全绿）。unit 2408 passed（较轮 2 的 2410 差 −2，与 a9 残留三例改一例 −2、t051 删一例 −1、t082 新增一例 +1 吻合），5 failed + 10 errors 与基线集逐条一致。integration 224 passed、7 errors（test_normal_exit_replay×4 + test_supervisor_start_capacity×1 + test_supervisor_status_truth×2，同为隔离 API 子进程就绪 setup 错误），三文件单跑 7/7 通过，定性负载 flake。重验后重新打勾，进审阅轮 2。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-21T13:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t097_code_f001|minor|已修|StreamContainerResidueError 生产已无抛出点、core 残留字典唯一写入点即其 except 分支，整条消费链为死代码且原「跨版本保留」理由不成立（字典仅进程内）；已删除 docker_adapter 的 StreamResidue/StreamContainerResidueError/cleanup_stream_residue、core 的字典/前置清理/except 分支，test_a9 三条残留用例改写为一条通用启动失败保端口用例、test_t051 直构脱敏用例删除|src/backend/cbrowser/supervisor/docker_adapter.py / core.py / tests/unit/test_a9_stream_residue.py / test_t051_docker_error_detail.py|
|t097_code_f002|minor|已修|runtime_lifecycle.md 权限与隔离节仍保留已废除的 Stream 规则集口径（Gateway 端点/UDP mux/白名单），与同文件新拓扑口径矛盾；已改写为拓扑决定可达面口径|docs/specs/runtime_lifecycle.md|
|t097_test_f001|minor|已修|伪造 role 用例删除后协议层无直接断言 stream 角色被拒；已在 test_t082_policy_agent 新增构造层与原始请求层双断言用例|tests/unit/test_t082_policy_agent.py|

### Round 2 (2026-11-21T14:08:00+08:00)

Round 2 两轴 PASS、零 finding；轮 1 三条 minor 经复核全部消除。

### Round 3 (2026-11-21T14:14:00+08:00)

Round 3 两轴 PASS、零 finding。本轮缘由：finish 严格 preflight 把 task.md 未知契约清单中 SPIKE 处置句内的字面标记词误计为未处置项，处置句改述为「原待实测 spike 项」（含义未动）后指纹变更，按流程重新审阅确认增量仅此一处。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-004/AC-005 按用户裁定打勾，真实验证延期本地 p160/p161；spike 处置登记 p159）
- 测试：门禁第三轮 gate-t097-final3b——protocol/requirements/design×2/contract/frontend_build/frontend_test exit 0；unit 2408 passed、5 failed + 10 errors 与云端基线集逐条一致；integration 224 passed、7 errors 为子进程就绪 flake（单跑 7/7 过）
- 黑盒：云端无 Docker/真实引擎，真机黑盒验证延期本地（p159/p160/p161）
- review：full 两轮，轮 2 code/test 均 PASS、零未处置 finding（轮 1 三条 minor 全部已修并经轮 2 复核消除）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Stream Policy Agent 与已安装规则全量删除，隔离改由 per-Profile internal 媒体网络声明式拓扑承担（ADR 041）；Browser Policy Agent 每 Profile 恰一个、改名 `<NNNN>-policy-agent` 并入 `<prefix>-profiles` 分组，存量旧形状/Stream Agent 在启动收敛与孤儿清理中删除或替换；协议与规则模型 role 收敛 browser-only；已无触发点的 Stream 残留机制整链删除。遗留：p159（spike 本地实测）、p160/p161（AC-004/005 本地补验）。

### 长期文档闭环

- specs runtime_lifecycle / webrtc_remote_display / browser_isolation / release_deployment 已更新口径并在 front matter 登记 t097；blueprint architecture / supervisor / testing 同步；新增 ADR 041（docs/blueprint/decisions/20261121_stream_topology_isolation.md）。spike 处置：原 UNVERIFIED-SPIKE 云端不可执行，处置结论与回退条件写入 task.md 与 ADR 041，实测登记 p159。
