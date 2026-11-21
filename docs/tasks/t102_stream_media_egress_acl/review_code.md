# Task review t102（reviewer_focus: 代码）

- task：`t102_stream_media_egress_acl`
- spec：`docs/tasks/t102_stream_media_egress_acl/task.md`
- diff_anchor：`190d652503cf5c2e9a6d14a91adc2f85d0df9547`
- target：`git diff 190d652503cf5c2e9a6d14a91adc2f85d0df9547`
- round：1
- reviewed_at：2026-11-21T20:24:09+08:00

reviewed_scope: 42f70632a2699c81

## Findings

### t102_code_f001 - Browser Agent 比对规则时丢失顺序

- 严重度：important
- 锚点：AC-002、AC-003，以及发布规范中「现有 Browser 策略精确一致时才接管」。
- 位置：`src/backend/cbrowser/supervisor/policy_agent.py:71`、`src/backend/cbrowser/supervisor/network_policy.py:105`、`src/backend/cbrowser/supervisor/network_policy.py:420`
- 问题：新 Agent 接管时，`verify_policy()` 返回真便保留现有内核规则。解析器用集合表示规则，交换同一 chain 内的 ACCEPT 与 DROP 仍得到相等结果。未配置代理的 Browser 依赖目的网段 DROP 位于宽泛 ACCEPT 之前。宽泛 ACCEPT 前移时，新 Agent 仍会接管，已有隔离和升级时的精确接管保证同时失效。
- 建议：按 chain 保存规范化后的有序规则，保留同一 chain 内的重复项。仅在规则语义和顺序一致时接管，保留现有不一致处理路径。

### t102_code_f002 - 启动对账可接管失去 ACL 的运行中 Stream

- 严重度：important
- 锚点：AC-002 的 Stream 出口拒绝，适用于接管后继续运行的 Stream。
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:1897`、`src/backend/cbrowser/supervisor/core.py:1246`、`src/backend/cbrowser/supervisor/core.py:1668`
- 问题：ACL 安装门禁保护创建和重建。Docker VM 防火墙重载移除 ACL 表且保留容器和网桥时，Supervisor 重启对账会将仍运行、已注册的 Stream 纳入 `_converge_session()`。媒体形状检查只读 Docker 元数据，Browser 策略验证与 Gateway 注册也可继续通过，因此有路由的 Stream 在缺少出口隔离时仍会恢复为 ready。旧 internal 网桥下由拓扑内在提供的隔离已改由独立内核状态提供。
- 建议：首次接管运行中 Stream 时一次性确认其桥级 ACL 有效。遇到缺失或无法确认的 ACL，停止旧 Stream，再走已有带启动门禁的 Stream-only 恢复路径。显式 readiness 应以同一出口隔离条件报告状态。此检查发生在接管和验收边界，无须引入持续规则巡检。

### t102_code_f003 - 媒体规范保留已失效的链路本地放行说明

- 严重度：minor
- 锚点：行为文档与 t102 实现不一致。
- 位置：`docs/specs/webrtc_remote_display.md:96`
- 问题：媒体规范的新段落写明只有固定 Gateway 信令和媒体 UDP 回复能通过，紧接的旧段落仍称媒体策略只放行链路本地范围，与实际 nft 规则矛盾。
- 建议：保留网络版本相关说明，删除失效的链路本地放行描述。

## 结论

- 本轮新发现：3 条。
- 未进表的提示：本轮净增且超过文件阈值的有 `src/backend/cbrowser/supervisor/docker_adapter.py`（3014 行）、`src/backend/cbrowser/supervisor/network_policy.py`（535 行）、`scripts/deploy.sh`（1410 行）、`tests/e2e/test_supervisor_offline_recovery_e2e.py`（694 行）、`tests/e2e/test_supervisor_recovery_e2e.py`（1215 行）、`tests/e2e/test_supervisor_retry_e2e.py`（665 行）、`tests/unit/test_t080_adapter_mounts.py`（614 行）。AC-001 采用目标 OrbStack 的 Mac 宿主发布边界。已存证据覆盖宿主回环发布，Docker VM 私有网桥内直接寻址属于不同入口，代码中 UDP 回复匹配只检查 mux 源端口、conntrack 状态和回复方向。
- 总体判断：Browser 策略接管可接受顺序不同的规则，Supervisor 重启可接管失去 ACL 的 Stream；AC-002、AC-003 的打勾作废。本轮执行静态复核，并查阅已有实机记录。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。已有 `clean_upgrade_viewer.log`、`clean_upgrade_matrix.log`、`clean_upgrade_agents.txt` 记录两个 Profile 的 Chrome 媒体、键盘、Gateway 信令、回环端口与 Browser-only Agent。
- AC-002：TICK-VOID，re_verified。代码证实新建安装失败封闭与已有拒绝矩阵对应正常路径，但 f001 和 f002 中的接管分支有独立缺口。
- AC-003：TICK-VOID，re_verified。隔离部署留存日志证实 v0.2.1 升级、回退与其它部署保持，f001 的静态复核证实升级代码不满足现有 Browser 策略精确接管契约。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-21T20:34:25+08:00)

reviewed_scope: b3527b11c75fb1a1

### Findings

#### t102_code_f004 - Supervisor 拒绝接管没有旧策略标记的 Stream

- 严重度：important
- 锚点：AC-003 的运行意愿、媒体与运行态收敛。Supervisor 重启后接管已启动的 Profile 同样经过该恢复路径。
- 位置：`src/backend/cbrowser/supervisor/core.py:1712`、`src/backend/cbrowser/supervisor/docker_adapter.py:2773`、`tests/e2e/test_supervisor_recovery_e2e.py:416`
- 问题：Supervisor 启动预检已成功重装桥级 ACL，接管分支仍要求 Browser 和 Stream 的 `policy_ready` 同为真。正常 Stream 无 `com.cbrowser.network-policy=v1`，扫描必返回假；控制面无法接管旧运行容器、恢复已占用 UDP 端口并记录会话。若持续超过宽限期，分支还会断开 Viewer 和清理沙箱。既有实机记录证实 ACL 与当前媒体可继续工作，针对运行态恢复的 SIGKILL E2E 仍失败（`t102_recovery_r2.log`）。
- 建议：接管分支只要求 Browser 的容器策略标记，Stream 接管使用 Supervisor 启动时的 ACL 安装结果和当前媒体形状，沿用原端口与会话接管流程。

#### t102_code_f005 - Policy Agent 协议 schema 描述仍使用旧隔离方式

- 严重度：minor
- 锚点：生成契约与实际模型描述一致。
- 位置：`schemas/runtime/policy_agent_protocol.json:27`、`src/backend/cbrowser/supervisor/network_policy.py:77`、`scripts/export_policy_agent_protocol.py:63`
- 问题：模型已改为说明 Stream 使用桥级 ACL，生成的 JSON schema 仍称隔离来自 internal 网络，与当前模型和实际行为冲突。
- 建议：用现有导出脚本重新生成该 schema。

### 结论

- 前轮 finding 复核：
    - `t102_code_f001` 已消除。两个地址族分别比较 chain 默认策略和有序规则序列，保留重复项。新 Agent 接管前仍要求核验成立。回归断言覆盖换序与重复规则（`src/backend/cbrowser/supervisor/network_policy.py:420`、`src/backend/cbrowser/supervisor/policy_agent.py:71`、`tests/unit/test_t026_network_policy_verify.py:70`）。
    - `t102_code_f002` 已消除原 ACL 缺口。Supervisor 先按部署归属筛选运行中的 Stream，校验当前形状的固定 IP 和回环 UDP 绑定，原子重装 ACL，再启动服务。安装失败会停止原 Stream。已有实机记录显示删除 ACL 后重启 Supervisor 恢复原规则，两条 Stream 仍使用原容器 ID（`src/backend/cbrowser/supervisor/runner.py:187`、`src/backend/cbrowser/supervisor/docker_adapter.py:1761`、`clean_restart_acl.log`、`clean_restart_shape.txt`）。
    - `t102_code_f003` 已消除。媒体规范描述当前桥级 ACL、重启恢复和失败停止行为，旧链路本地放行段落已删除（`docs/specs/webrtc_remote_display.md:95`）。
- 本轮新发现：2 条。
- 未进表的提示：本轮净增且超过文件阈值的有 `src/backend/cbrowser/supervisor/docker_adapter.py`（3050 行）、`src/backend/cbrowser/supervisor/network_policy.py`（535 行）、`src/backend/cbrowser/supervisor/runner.py`（757 行）、`scripts/deploy.sh`（1410 行）、`tests/e2e/test_supervisor_offline_recovery_e2e.py`（694 行）、`tests/e2e/test_supervisor_recovery_e2e.py`（1215 行）、`tests/e2e/test_supervisor_retry_e2e.py`（665 行）、`tests/unit/test_t080_adapter_mounts.py`（614 行）。
- 总体判断：三项前轮缺口已修。R2 仍有运行态接管阻断。部署态结论取自留存的 R2 实机和 E2E 原始记录，本轮未操作 Docker 或另跑部署验收。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。R2 原始记录 `clean_restart_viewer.log`、`clean_restart_matrix.log`、`clean_upgrade_agents.txt`、`t102_direct_udp_probe.log` 验证两 Profile 的视频、音频、输入、Gateway 信令、仅 Browser Agent 以及 Mac 私网直达和回环发布差异。
- AC-002：TICK-VALID，re_verified。独立查证创建与接管顺序、固定端点桥级过滤、IPv6 禁用和 Browser 规则保序断言，另以 `clean_restart_matrix.log`、`clean_restart_acl.log` 与 `fail_closed_r2.log` 核对部署态拒绝、恢复和失败封闭。
- AC-003：TICK-VOID，re_verified。已有 R2 实机记录支持 v0.2.1 切换、两条媒体及代理和另一部署保持，但代码与现有 SIGKILL E2E 都证实 f004 的运行态接管缺口。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 3 (2026-11-21T20:44:45+08:00)

reviewed_scope: 1091f65c5de215bd

### Findings

无新增发现。

### 结论

- 前轮 finding 复核：
    - `t102_code_f004` 已消除。启动对账只检查 Browser 的 per-container 策略标记。仍运行的 Stream 在 Supervisor 启动服务前恢复桥级 ACL，随后经原流程接管 UDP 端口和会话。R3 的两个 Profile 在删除 ACL、重启 Supervisor 后 readiness 均为 true，Browser 和 Stream ID 前后一致。此前失败的 SIGKILL 恢复 E2E 已通过（`src/backend/cbrowser/supervisor/core.py:1714`、`src/backend/cbrowser/supervisor/core.py:1792`、`src/backend/cbrowser/supervisor/runner.py:190`、`clean_restart_readiness.log`、`t102_recovery_r3.log`）。
    - `t102_code_f005` 已消除。生成的 schema 只更新 `NetworkPolicySpec.description`，描述与源码相同。协议漂移门禁退出 0（`schemas/runtime/policy_agent_protocol.json:27`、`src/backend/cbrowser/supervisor/network_policy.py:77`、`t102_r3_gate.log`）。
    - `t102_code_f001`、`t102_code_f002`、`t102_code_f003` 的修复仍在当前交付中。核对了按链保序与重复项、启动时恢复或停止、媒体规范同步。
- 本轮新发现：0 条。
- 未进表的提示：净增且超过文件阈值的有 `src/backend/cbrowser/supervisor/docker_adapter.py`（3050 行）、`src/backend/cbrowser/supervisor/network_policy.py`（535 行）、`src/backend/cbrowser/supervisor/runner.py`（757 行）、`scripts/deploy.sh`（1410 行）、`tests/e2e/test_supervisor_offline_recovery_e2e.py`（694 行）、`tests/e2e/test_supervisor_recovery_e2e.py`（1213 行）、`tests/e2e/test_supervisor_retry_e2e.py`（665 行）、`tests/unit/test_t080_adapter_mounts.py`（614 行）。生成的协议 schema 排除于文件尺寸检查。
- 总体判断：R3 代码轴通过，前轮发现均已修复。复审静态代码和原始实机记录，未另跑 Docker 验收。全量 E2E 在复审时尚未结束，已有六项恢复与重试 E2E 通过。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。R3 的 `clean_restart_viewer.log`、`clean_restart_matrix.log` 与 `clean_upgrade_agents.txt` 记录双 Profile 回环 UDP、视频音频、键盘输入、Gateway 信令及 Browser-only Agent。
- AC-002：TICK-VALID，re_verified。静态核对创建和接管均先安装 ACL、失败分支收住 Stream、IPv6 禁用及 Browser 策略按链保序，部署行为依据 `clean_restart_matrix.log`、`clean_restart_acl.log`、`fail_closed_r3.log`。
- AC-003：TICK-VALID，trust_prior。R3 升级、重启和回退日志记录两 Profile 持久化标记与运行意愿、完整 readiness、媒体及旧版代理恢复，另有 `clean_rollback_acl.log` 和 `clean_formal_unchanged.log` 确认 ACL 清理和另一部署 16 容器保持。

coverage = 1 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS

## Round 4 (2026-11-22T00:54:51+08:00)

reviewed_scope: 936adcc46540c1ec

### Findings

无新增发现。

### 结论

- 前轮 finding 复核：`t102_code_f001` 的 Browser 规则按链保序及重复项校验、`t102_code_f002` 的启动前 ACL 恢复与失败停止、`t102_code_f003` 的媒体出口规范、`t102_code_f004` 的 Browser-only 恢复门禁和 `t102_code_f005` 的生成 schema 修复均保持。运行实现、镜像构建和部署脚本的 Git 内容与 R3 一致。
- 本轮新发现：0 条。
- 未进表的提示：文件尺寸沿用 R3 清单，新增达到提示阈值的 `tests/e2e/test_supervisor_container_graph_e2e.py` 为 911 行。原始 E2E 为 104 通过、2 失败、2 默认跳过。旧容器图节点由现行语义节点替换后专项通过，跨 IPC 探针原样专项复跑通过，首次失败原因未定位。两项专项通过与原始 E2E 结果分别留档。
- 总体判断：R4 代码轴通过。容器图测试保留 Gateway、凭据隔离和实例围栏等业务断言，并要求 Browser gate、仅 Browser Policy Agent、Stream 媒体桥及 IPv6/DNS 配置（`tests/e2e/test_supervisor_container_graph_e2e.py:67`、`tests/e2e/test_supervisor_container_graph_e2e.py:490`）。核对原始门禁和部署验收清单的六个镜像身份一致。本轮只做静态审查和既有证据核对。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。原始实机记录 `clean_restart_viewer.log`、`clean_restart_matrix.log` 与 `clean_upgrade_agents.txt` 证实两 Profile 回环 UDP、视频音频、键盘、Gateway 信令和 Agent 形状，新容器图节点的同镜像专项也通过（`t102_graph_r4.log`）。
- AC-002：TICK-VALID，re_verified。静态复核固定端点桥级过滤、先安装再创建及接管、IPv6 配置及 Browser 规则保序，结合 `clean_restart_matrix.log`、`clean_restart_acl.log` 与 `fail_closed_r3.log` 复核实际拒绝、恢复和失败封闭。
- AC-003：TICK-VALID，trust_prior。相同镜像的 `clean_upgrade_deploy.log`、`clean_restart_readiness.log`、`clean_rollback_deploy.log`、`clean_rollback_matrix.log` 与 `clean_formal_unchanged.log` 记录旧 release 往返、运行态收敛、回退后旧版代理恢复以及其它部署 16 个容器保持，Profile 数据保留由实机 Viewer 标记核对。

coverage = 1 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS

## Round 5 (2026-11-22T00:59:20+08:00)

reviewed_scope: 936adcc46540c1ec

### Findings

无新增发现。

### 结论

- 前轮 finding 复核：R4 已确认 `t102_code_f001` 至 `t102_code_f005` 修复。本轮代码、测试和镜像构建脚本与 R4 一致。
- 本轮新发现：0 条。
- 未进表的提示：沿用 R4 文件尺寸与门禁记录。
- 总体判断：s028 的补记准确反映原测量结论。目标 OrbStack 的 internal 网桥无法发布回环端口，普通网桥对照成功，d054 支持该决定。后续 t102 用可路由媒体网桥恢复回环 UDP，并用网桥 ACL 维持出口拒绝（`docs/spikes/s028_t097_media_topology_orbstack/report.md:53`、`docs/findings/d054_orbstack_internal_network_drops_published_ports.md:4`、`docs/blueprint/decisions/20261121_stream_topology_isolation.md:16`）。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。R4 核对的同镜像实机媒体、Gateway 与 Agent 形状证据仍适用。
- AC-002：TICK-VALID，re_verified。静态核对创建与接管前桥级 ACL、失败停止和 Browser 保序验证，沿用实机拒绝矩阵与失效负例。
- AC-003：TICK-VALID，trust_prior。R4 核对的旧版升级、重启与回退日志仍适用，记录 Profile 状态、媒体、代理及另一部署归属。

coverage = 1 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS
