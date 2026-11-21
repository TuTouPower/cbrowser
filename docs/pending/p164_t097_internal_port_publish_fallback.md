---
pid: "p164"
slug: "t097_internal_port_publish_fallback"
status: "todo"
---
# p164 t097 回退：internal 网桥丢弃发布端口，需可路由媒体网加声明式出口 ACL

- 来源：s028 / d054 / p159 本地实测（2026-11-21）。t097 ADR `docs/blueprint/decisions/20261121_stream_topology_isolation.md`「验证与回退」已触发。
- 内容：目标 OrbStack arm64 / Docker 29.4.0 上，`--internal` 网桥上的容器所有已发布端口（TCP/UDP）被静默丢弃（`docker port` 未发布、inspect `Ports=null`、宿主无监听），而生产 `start_stream_container` 把 Stream 仅挂该 internal 网并传 `ports=stream_ports()`（`docker_adapter.py:2462-2477`），故宿主 Chrome 的媒体回环入口不成立（AC-004 真机失败）。按 ADR 回退条件：媒体网改回可路由 bridge，同时以等价声明式手段恢复 Stream 对公网/局域网/宿主其它服务/Browser 其它网络/其它 Profile 的出站拒绝（网络级出口 ACL），不得恢复 Stream Policy Agent 与命令式规则巡检。保持 UDP mux 仅发布 `127.0.0.1`（ADR 031/t054 口径）。改造须同步 t097 ADR、`docs/specs/webrtc_remote_display.md`、`docs/specs/browser_isolation.md` 与 `docs/blueprint/architecture.md` 并登记新 task 实施。
- 处理：未开（待立项；实施后按 s028 同法重验宿主回环 UDP 发布与拒绝矩阵，并补 p160/p161 部署级验证）
