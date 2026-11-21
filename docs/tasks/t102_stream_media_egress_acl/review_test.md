# Task review t102（reviewer_focus: 测试）

- task：`t102_stream_media_egress_acl`
- spec：`docs/tasks/t102_stream_media_egress_acl/task.md`
- diff_anchor：`190d652503cf5c2e9a6d14a91adc2f85d0df9547`
- target：`git diff 190d652503cf5c2e9a6d14a91adc2f85d0df9547`
- round：1
- reviewed_at：2026-11-21T20:22:11+08:00

reviewed_scope: 42f70632a2699c81

## Findings

### t102_test_f001 - Supervisor 恢复 E2E 启动失败时遗留 Gateway relay

- 严重度：important
- 锚点：行为缺陷。直接运行恢复 E2E 时，Supervisor 启动报错后，新建的 Docker relay 仍运行。
- 位置：`tests/e2e/test_supervisor_recovery_e2e.py:341`、`tests/e2e/test_supervisor_recovery_e2e.py:589`、`tests/e2e/test_supervisor_recovery_e2e.py:858`、`tests/fixtures/supervisor_recovery_probe/gateway_service.py:217`
- 问题：三处先创建脱离进程运行的 relay，再执行可能抛异常的 `sup.start()`，之后才进入调用 `gateway.stop()` 和清理专属前缀的 `try/finally`。第一处的初次 Profile 启动与断言也在清理范围外。直接运行 pytest 时没有 Gate run 标签，外层 API fixture 仅关停宿主子进程，未清理该 relay。
- 建议：从 relay 创建开始纳入测试自己的 `try/finally`，确保 Supervisor 启动或首次 Profile 断言失败后仍清理专属 relay。保留现有失败断言。

## 结论

- 改测方向复核：网络断言随契约改为检查 routable bridge、旧标签不兼容、固定 IP、Stream 入口和 ACL 先后顺序。模拟 Docker 失败的测试触达生产启动逻辑。真实辅助镜像缺失和端口释放分别有独立记录。Gateway 夹具使用实际生产 Gateway、以 TCP 转发接入受管网桥，原媒体与恢复断言未删。自定义 UDP 基址的参数化保留默认行为。未发现新增 skip、超时放宽或用 DOM 赋值替代键盘输入。
- 本轮新发现：1 条。
- 未进表的提示：前次全量门禁暴露 UDP 默认基址和 Gateway 夹具问题。后续策略失败与端口释放专项通过。最终全套门禁在运行，当前证据不足以宣称全套通过。实机证据使用目标 OrbStack。
- 总体判断：三条 AC 的实机证据可采信。恢复 E2E 新增的 Docker relay 未覆盖异常路径清理。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。核对主仓 `.scratch/t102_evidence/acceptance` 的实机 Chrome 日志和探针，双 Profile 经回环 UDP 接收实际视频和音频，键盘输入抵达 Browser，Gateway 可达，升级后只有两只 Browser Agent。
- AC-002：TICK-VALID，trust_prior。核对实机拒绝矩阵及同目标可达基线、IPv6/DNS、直连与显式代理进程配置及真实的缺辅助镜像负例，并核对自动测试断言与生产顺序。
- AC-003：TICK-VALID，trust_prior。核对真实 v0.2.1 往返中两个 Profile 文件标记与运行意愿、Browser ID、单/双 Agent 拓扑、媒体和代理恢复、已撤销 ACL 清理以及另一部署 16 个运行容器 ID 不变的证据。

coverage = 0 / 3

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-21T20:35:26+08:00)

reviewed_scope: b3527b11c75fb1a1

## Findings

### t102_test_f002 - SIGKILL 恢复仍要求 Stream 的旧策略标记

- 严重度：important
- 锚点：行为缺陷。运行中 Profile 的 Supervisor 重启后，即使 Stream 桥 ACL 已恢复，控制面仍不能把现有会话收敛到 running。
- 位置：`tests/e2e/test_supervisor_recovery_e2e.py:416`、`src/backend/cbrowser/supervisor/core.py:1712`、`src/backend/cbrowser/supervisor/docker_adapter.py:2773`
- 问题：恢复 E2E 首项失败，日志记录重启后不断轮询 Profile status，并报 `Unprotected sandbox awaiting policy`。无现有内存 session 的恢复分支同时要求 Browser 与 Stream 的 `policy_ready`，而后者没有 v1 策略标签或 ready marker。真实 R2 演练证明 Supervisor 重启能补装 ACL、原容器 Viewer 仍能解码，但该阶段未调用 Supervisor readiness，无法否定恢复断言失败。
- 建议：接管时只用已有 gate 判定 Browser，Stream 按桥级 ACL 与媒体拓扑验收；复跑 SIGKILL 恢复 E2E，并在真实 ACL 丢失演练中核对 Supervisor 确实恢复了会话和 readiness。

## 结论

- 前轮 finding 复核：`t102_test_f001` 部分修复。三处 relay 与 Supervisor 启动都已置于 finally 覆盖，第一处的早期 Profile 断言也纳入。前两处 finally（`tests/e2e/test_supervisor_recovery_e2e.py:486`、`:714`）仍依次等待 Supervisor、Gateway 与按前缀清理。Supervisor 某一步停机、取日志或删除失败时，`RealSupervisorContainer.stop()` 会抛错并跳过独立 relay 的清理。第三处 teardown 已分步捕获异常。前两处同样应确保每一步均有执行机会并保留异常结果。
- 改测方向复核：有序规则的两项参数化用例在内核规则读取边界分别模拟 ACCEPT 前移和重复，触达生产解析与策略比较。Stream 启动接管用例只替换 Docker 边界，检查 ACL 恢复失败时具体容器收到停止请求。恢复 E2E 原断言保留且揭示了真实回归。
- 本轮新发现：1 条。
- 未进表的提示：现有 35 项专项单元通过。最终门禁的 `protocol_drift_check` 已退出 1，Policy Agent 生成 schema 稳定性检查报告 stale，其它套件仍在执行。6 项恢复 E2E 已看到首项失败，余项尚未完成。
- 总体判断：真实部署的三条 AC 有证据支持，异常清理及 SIGKILL 恢复问题尚未关闭，完整项目门禁未通过。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。R2 Chrome 日志证实双 Profile 均经回环 UDP 收到真实视频和音频并可输入，所绑定的 Gateway 信令可达，容器清单只有两个 Browser Agent。
- AC-002：TICK-VALID，trust_prior。R2 已归档同目标可达基线与拒绝矩阵、辅助镜像失效不创建 Stream、Mac 不能直连 Stream 私有地址；删 ACL 后真实 Supervisor 进程重启补装，并重验媒体与拒绝矩阵。
- AC-003：TICK-VALID，trust_prior。R2 v0.2.1 与 t102-r2 往返通过，前后核对 Profile 持久文件、运行意愿、Browser 身份、单/双 Agent 形状、旧媒体与代理和另一部署 16 个容器未变。

coverage = 0 / 3

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 3 (2026-11-21T20:44:58+08:00)

reviewed_scope: 1091f65c5de215bd

## 结论

- 前轮 finding 复核：`t102_test_f001` 已修。前两处 `AsyncExitStack` 在创建 relay 前分别注册 Supervisor 停机、Gateway 停机、精确前缀清理与 Docker 客户端关闭。任一回调报错时仍执行余项。第三处逐项执行并保留异常。pytest 原有按前缀 finalizer 也提供资源清理补偿。
- 前轮 finding 复核：`t102_test_f002` 已修。恢复已有会话的旧 gate 仅判定 Browser，Stream ACL 由 Supervisor 在开始服务前重装。原 SIGKILL 恢复断言及其余专项均通过，真实 R3 ACL 丢失演练同时有两个 Profile 的控制面 readiness、容器身份和 Viewer 实测记录。
- 改测方向复核：恢复 E2E 保留原健康、状态、UDP 和事件断言，改动只扩大异常清理范围。Policy Agent 生成协议更新仅同步描述，字段和校验类型无变化，协议漂移检查退出 0。
- 本轮新发现：0 条。
- 未进表的提示：专项恢复、重试、离线及清理共 6 项通过。R3 项目门禁中的协议、依赖、模板、后端、前端、构建与镜像依赖套件均退出 0；全量 E2E 在出具报告时尚未结束。
- 总体判断：R1、R2 测试 finding 已关闭，最终实机证据支持三条 AC。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。最终实机记录显示两条 Chrome 会话均经宿主回环 UDP 收到视频和音频并正确传入键盘，本 Profile Gateway 可达，升级后只有两个 Browser Agent。
- AC-002：TICK-VALID，trust_prior。最终实机的拒绝矩阵、可达基线、IPv6/DNS、直连与显式代理，以及辅助镜像失效拒绝创建 Stream 均有记录；删去 ACL 并重启 Supervisor 后，桥规则、拒绝矩阵和原 Profile 的 readiness 重新验证。
- AC-003：TICK-VALID，trust_prior。最终 v0.2.1 与 t102-r3 往返验证 Profile 文件标记、运行意愿、旧版媒体和代理恢复，删除两张废弃 ACL，并核对另一部署 16 个容器身份及运行状态。

coverage = 0 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS

## Round 4 (2026-11-22T00:54:42+08:00)

reviewed_scope: 936adcc46540c1ec

## 结论

- 前轮 finding 复核：`t102_test_f001` 和 `t102_test_f002` 保持已修。R4 未修改恢复清理或生产接管流程，R3 的 6 项恢复、重试与离线实测证据仍适用。
- 改测方向复核：容器图旧节点要求 Stream 使用已撤销的 per-container gate。替代节点保留 Browser 就绪标记、Gateway 权威端口、凭据与 Socket 隔离、跨 Profile TCP 探测及其正对照、Viewer 关闭与实例 fencing、SIGKILL 后容器身份和端口断言。新增实际 Docker 对象的媒体桥、Stream IPv6/DNS 和每 Profile 仅一个 Browser Agent 断言。无新增跳过、阈值放宽或被测逻辑替身。
- 本轮新发现：0 条。
- 未进表的提示：原始统一门禁各非 E2E 套件通过，E2E 原始记录 104 通过、2 失败、2 跳过，manifest 仍标记失败。改造后的容器图节点与原样的 Browser 跨 IPC 节点分别单跑通过，原失败记录和两份重跑 JUnit 均保留。跨 IPC 首次异常成功的原因未定位。同最终镜像的组合结果为 106 通过、2 跳过。
- 总体判断：容器图新节点覆盖实际角色拓扑并保留既有业务断言。独立实机验收和复跑证据支持三条 AC。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。最终镜像的实机 Chrome 两条会话均由宿主回环 UDP 解码视频、接收音频并传递键盘，Gateway 可达，容器图复跑核实仅 Browser 挂策略 gate 且每个 Profile 只运行一个 Browser Agent。
- AC-002：TICK-VALID，trust_prior。最终镜像实机记录拒绝矩阵、同目标可达对照、IPv6/DNS、代理与直连限制、辅助镜像失效不创建 Stream。实机删 ACL 后重启确认两个原 Profile 恢复 readiness 并重验拒绝矩阵，容器图检查两角色的跨 Profile 连接拒绝与本地正对照。
- AC-003：TICK-VALID，trust_prior。v0.2.1 与最终镜像往返核对 Profile 文件、运行意愿、旧版媒体和代理恢复、两张废弃 ACL 清理与另一部署的 16 个容器不变，真实恢复 E2E 核对运行中 Profile 的端口和容器身份。

coverage = 0 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS

## Round 5 (2026-11-22T00:59:05+08:00)

reviewed_scope: 936adcc46540c1ec

## 结论

- 前轮 finding 复核：`t102_test_f001` 和 `t102_test_f002` 保持已修。
- 改测方向复核：无测试变更。s028 补记的决定与原实测一致。目标 OrbStack 的 internal 网桥无法发布宿主回环端口，后续 t102 改为普通媒体桥并为 Stream 保留网桥级出口拒绝。归档保留原始 E2E 104 通过、2 失败、2 跳过及两项单独复验通过，IPC 首次异常未定因。
- 本轮新发现：0 条。
- 总体判断：历史结论补记与最终实机证据一致，R4 判定继续有效。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。最终实机 Chrome 视频、音频、键盘和 Gateway 记录验证回环 UDP 媒体，容器图复验核实每个 Profile 仅有一个 Browser Agent。
- AC-002：TICK-VALID，trust_prior。最终拒绝矩阵、同目标可达对照、辅助镜像失效和 ACL 恢复后的 readiness 均有实机证据。
- AC-003：TICK-VALID，trust_prior。真实升级回退保留 Profile 文件和运行意愿，恢复旧版媒体和代理，另一部署的 16 个容器保持原样。

coverage = 0 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS
