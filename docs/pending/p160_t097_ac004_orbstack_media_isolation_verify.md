---
pid: "p160"
slug: "t097_ac004_orbstack_media_isolation_verify"
status: "closed"
resolution: "resolved"
reason: "2026-11-21 本地 OrbStack 实测完成：隔离矩阵（Gateway 信令、公网/局域网/宿主服务/其它 Profile/IPv6 拒绝）由 internal 拓扑成立；宿主回环 UDP 媒体入口在 internal 网桥上失效（d054），AC-004 整体不通过，回退改造登记 p164。"
fix_ref: "s028"
---
# p160 t097 AC-004 本地补验：OrbStack 真机媒体与 Stream 隔离矩阵

- 来源：t097 AC-004 [deploy] 的云端处置注记（云端无 Docker 与真实 Chrome，AC 已按用户裁定打勾、真实验证延期本地）
- 内容：目标 OrbStack 上，本机 Chrome 能观看、收听和操作同一个 Profile，媒体只从宿主回环入口接收；Stream 只使用约定的 Gateway 信令与本机媒体通道；隔离验证覆盖公网、局域网、宿主其它服务、Browser 与其它 Profile 的网络边界及有 IPv6 时的双栈行为；网络配置失配时不得把越界的 Stream 标记为可用。记录网络端点、运行资源身份与 Chrome 媒体结果。
- 处理：闭环（resolved，2026-11-21）。真机验证由 s028 隔离最小拓扑（`docs/spikes/s028_t097_media_topology_orbstack/report.md`）在目标 OrbStack arm64 / Docker 29.4.0 上完成，全部资源以 `probe-s028*` 前缀隔离并清理，未触碰运行中部署与 t100 worktree。
    - 隔离矩阵（PASS）：媒体网形状为 `internal=true` + bridge + 显式 subnet `10.220.0.0/24`；Stream↔Gateway 同网 TCP 连通；Stream 对其它 Profile 网、宿主/LAN 服务网、公网 IPv4 `1.1.1.1:443`、公网 IPv6 `2606:4700:4700::1111:443` 全部拒绝；有 IPv6 地址但无外部 IPv6 出口。即「Stream 仅用约定 Gateway 信令 + 本网媒体、越界不可达」成立。
    - 媒体入口（FAIL）：宿主 `127.0.0.1:<udp_mux>` 不可达、无回包；对照实验证明 internal 网桥上 Docker 静默丢弃所有已发布端口（TCP/UDP），普通网桥同参数立即生效（d054）。生产 `start_stream_container` 正是把 Stream 仅挂 internal 网并发布 127.0.0.1 UDP 端口，故本机 Chrome 的观看/收听/操作入口不成立。
    - 结论：AC-004 整体判定**不通过**（媒体失败、隔离成立）。按 t097 ADR 回退条件已登记 p164：媒体网改回可路由 bridge 并以等价声明式手段恢复 Stream 出站拒绝（网络级出口 ACL），不得恢复 Stream Policy Agent。p164 实施后须按本条矩阵重验（含真实 Chrome Viewer 首帧与音频），方可把 AC-004 改判通过。
    - 可信度说明：本验证为隔离最小拓扑（轻量容器 + 真实 Docker internal 网 + 真实端口发布），精确复现了生产 Stream 的网络与端口声明（`docker_adapter.py:2462-2477`），证据强于源码推断；Chrome Viewer 端到端首帧在媒体入口不成立的前提下无验证意义，故未执行，不冒充已验。
