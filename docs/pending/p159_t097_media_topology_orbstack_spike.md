---
pid: "p159"
slug: "t097_media_topology_orbstack_spike"
status: "todo"
---
# p159 t097 spike 本地执行：OrbStack 最小拓扑实测

- 来源：t097 契约 UNVERIFIED-SPIKE 的云端处置（云端无 Docker/OrbStack，spike 无法在云端执行）
- 内容：在目标 OrbStack 上用隔离最小拓扑实测——per-Profile 媒体网络设为 internal 后，宿主回环 UDP 发布（Stream UDP mux 端口映射到 127.0.0.1）是否仍可达且回包正常、Gateway 信令（Stream↔Gateway 同网）是否正常、Stream 对公网/局域网/宿主其它服务/Browser 网络边界/其它 Profile 的出站是否被拓扑本身拒绝；有 IPv6 时记录双栈行为。现有 Stream 规则允许链路本地媒体回包，不能从回环发布直接推导等价拓扑，必须以实测矩阵为准。若实测不成立，按 t097 ADR 记录的回退条件修订声明式拓扑。
- 处理：未开（留待本地 Mac 执行；结论回填 t097 ADR 与 docs/specs/webrtc_remote_display.md）
