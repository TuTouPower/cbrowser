---
pid: "p159"
slug: "t097_media_topology_orbstack_spike"
status: "closed"
resolution: "resolved"
reason: "2026-11-21 本地 OrbStack 实测完成：宿主回环 UDP 发布在 internal 网桥上失效（d054），Gateway 信令与出站拒绝矩阵由拓扑成立；结论入 s028 报告、d054 finding，并回写 t097 ADR 与 webrtc_remote_display spec；回退改造登记 p164。"
fix_ref: "s028"
---
# p159 t097 spike 本地执行：OrbStack 最小拓扑实测

- 来源：t097 契约 UNVERIFIED-SPIKE 的云端处置（云端无 Docker/OrbStack，spike 无法在云端执行）
- 内容：在目标 OrbStack 上用隔离最小拓扑实测——per-Profile 媒体网络设为 internal 后，宿主回环 UDP 发布（Stream UDP mux 端口映射到 127.0.0.1）是否仍可达且回包正常、Gateway 信令（Stream↔Gateway 同网）是否正常、Stream 对公网/局域网/宿主其它服务/Browser 网络边界/其它 Profile 的出站是否被拓扑本身拒绝；有 IPv6 时记录双栈行为。现有 Stream 规则允许链路本地媒体回包，不能从回环发布直接推导等价拓扑，必须以实测矩阵为准。若实测不成立，按 t097 ADR 记录的回退条件修订声明式拓扑。
- 处理：s028；resolution=resolved；reason=2026-11-21 本地 OrbStack 实测完成：宿主回环 UDP 发布在 internal 网桥上失效（d054），Gateway 信令与出站拒绝矩阵由拓扑成立；结论入 s028 报告、d054 finding，并回写 t097 ADR 与 webrtc_remote_display spec；回退改造登记 p164。
