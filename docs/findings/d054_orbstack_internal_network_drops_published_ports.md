# d054 OrbStack internal 网桥不承载已发布端口，t097 媒体回环发布失效

- 来源：s028，实测于 2026-11-21（目标 OrbStack arm64 / Docker Engine 29.4.0）。 [Spike 报告](../spikes/s028_t097_media_topology_orbstack/report.md)
- 结论：`docker network create --internal` 创建的网桥上，`docker run -p 127.0.0.1:<port>:<port>[/udp|/tcp]` 被守护进程静默丢弃——`docker port` 报 `no public port ... published`、inspect 的 `Ports` 为 `null`、宿主 `127.0.0.1:<port>` 无监听；同一镜像与发布参数在普通（非 internal）网桥上立即生效（TCP 与 UDP 均验证）。因此把 per-Profile 媒体网络设为 internal 后，t097 依赖的「Stream UDP mux 发布到宿主 127.0.0.1」不成立。
- 证据：隔离最小拓扑（专属 `probe-s028*` 前缀，finally 清理）。internal 网 `10.220.0.0/24`：internal=true、driver=bridge、subnet 正确；Stream 与同网 Gateway TCP 连通（`true`），对其它 Profile 网、宿主/LAN 服务网、公网 IPv4 `1.1.1.1:443`、公网 IPv6 `2606:4700:4700::1111:443` 均拒绝（`false`）；有 IPv6 地址但无外部 IPv6 连接。宿主回环 UDP 发布超时（`FAIL: timed out`）。对照实验：普通网桥同参数 `docker port` 返回 `127.0.0.1:<port>`，宿主收到 `ECHO:<payload>`。
- 影响：t097 ADR 的「回环发布与 internal 等价」前提不成立，触发表内回退条件。AC-004 的真机媒体访问在当前声明式拓扑下失败；Gateway 信令与隔离拒绝矩阵本身成立。按 ADR：媒体网改回可路由 bridge 的同时须以等价声明式手段恢复 Stream 出站拒绝（网络级出口 ACL），不得恢复 Stream Policy Agent 与命令式规则巡检；该改造尚未实施（登记 p164）。
- 现状：有效（待 p164 回退实施后重验）
