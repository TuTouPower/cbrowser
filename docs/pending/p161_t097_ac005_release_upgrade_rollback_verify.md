---
pid: "p161"
slug: "t097_ac005_release_upgrade_rollback_verify"
status: "parked"
reason: "2026-11-21 本地真机补验部分完成但升级半程受阻：已核实当前运行 release 20261120232230-369d98d 确为两类 Agent 旧形状（3 Profile 共 6 个 policy-agent + 6 个 sandbox，媒体网为可路由 bridge）。尝试从当前源码构建新 release 做真实升级/回退，两次 deploy 均因 apt 源经代理 0.250.250.254:7890 返回 502 Bad Gateway 而构建失败；deploy 在任何状态变更/指针移动前中止，old release 仍为 current、16 个运行中容器未受影响，残留 API 镜像已清理。暂停等待构建网络恢复；且新拓扑媒体入口失效（d054/p164），升级半程的媒体与代理功能恢复须在 p164 实施后一并重验。"
---
# p161 t097 AC-005 本地补验：旧 release 升级收敛与回退

- 来源：t097 AC-005 [deploy] 的云端处置注记（云端无 Docker，AC 已按用户裁定打勾、真实验证延期本地）
- 内容：隔离部署从仍有两类 Agent 的 release 升级后，运行意愿和 Profile 数据保留，所有受影响环境按新形状收敛且无旧 Agent 残留；回退到受支持的上一 release 后，原有媒体和 Browser 代理功能恢复，且无跨部署清理。
- 处理：parked（2026-11-21）。真机起始态已核实：当前 release `20261120232230-369d98d` 为两类 Agent 旧形状（3 Profile 共 6 个 `<NNNN>-policy-agent` + 6 个 browser/stream sandbox，媒体网为可路由 bridge），满足 AC-005 升级前条件；回退目标 release manifest 与全部镜像本地完整。真实升级/回退未执行：当前源码构建新 release 两次均在 browser 镜像 apt 层因代理 502 失败（日志 `.scratch/p161_deploy.log` / `.scratch/p161_deploy_retry.log`），deploy 在任何容器变更与指针移动前中止，old release 仍为 current、16 个运行中容器未受影响、残留 API 镜像已清理。按有限重试与容错原则停止重试。恢复条件：构建网络恢复且 p164（internal 网桥丢弃发布端口导致媒体入口失效）实施后，再完成升级形状收敛、数据保留、无旧 Agent 残留与回退后媒体/代理恢复的真实验证，届时复活本条并闭环。
- 暂搁：2026-11-21 本地真机补验部分完成但升级半程受阻：已核实当前运行 release 20261120232230-369d98d 确为两类 Agent 旧形状（3 Profile 共 6 个 policy-agent + 6 个 sandbox，媒体网为可路由 bridge）。尝试从当前源码构建新 release 做真实升级/回退，两次 deploy 均因 apt 源经代理 0.250.250.254:7890 返回 502 Bad Gateway 而构建失败；deploy 在任何状态变更/指针移动前中止，old release 仍为 current、16 个运行中容器未受影响，残留 API 镜像已清理。暂停等待构建网络恢复；且新拓扑媒体入口失效（d054/p164），升级半程的媒体与代理功能恢复须在 p164 实施后一并重验。
