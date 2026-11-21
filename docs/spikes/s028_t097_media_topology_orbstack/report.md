---
slug: "t097_media_topology_orbstack"
status: "completed"
sid: "s028"
---

# Spike report: t097 媒体网络 internal 拓扑的 OrbStack 最小实测（p159）

## 问题

t097 把 per-Profile 媒体网络改为 `bridge + internal + 显式 subnet`，Stream 不设 Policy Agent，隔离改由拓扑承担；同时 Stream 的 UDP mux 仍按 ADR 031/t054 发布到宿主 `127.0.0.1`。p159 要求在目标 OrbStack 上实测「internal 媒体网 + 宿主回环 UDP 发布」是否等价，以及 Gateway 信令与出站拒绝矩阵是否由拓扑本身成立。云端无 Docker/OrbStack，无法执行。

## 成功判据

- 宿主 `127.0.0.1:<udp_mux>` 可达且回包正常。
- Stream↔Gateway（同 internal 网）信令可达。
- Stream 对公网、局域网/宿主其它服务、其它 Profile 网、Browser 网的出站由拓扑拒绝；有 IPv6 时记录双栈行为。
- 实测不成立时按 t097 ADR 回退条件修订声明式拓扑。

## 尝试

- 2026-11-21，目标 Mac M1 Max / OrbStack arm64 / Docker Engine 29.4.0。`code/topology_probe.py` 用专属 `probe-s028*` 前缀创建三个网：`probe-s028-media`（`--internal --subnet 10.220.0.0/24`）、`probe-s028-other`（另一个 Profile，`internal`）、`probe-s028-uplink`（普通网桥，模拟宿主/LAN/公网路径）。
- `gateway` 容器挂媒体网 `10.220.0.10`（TCP 8005），`stream` 容器挂媒体网 `10.220.0.20` 并以 `-p 127.0.0.1:30123:30123/udp` 发布 UDP，`peer` 挂另一 Profile 网 `10.221.0.20`，`svc` 挂 uplink 网 `10.222.0.20`。`code/udp_echo.py` 在 Stream 内提供 UDP 回显。宿主与各方向的连接结果由脚本汇总；所有容器与网在 `finally` 中销毁。
- 为排除「探针搭建错误」的可能，另在 `.scratch/s028_udp_diag.sh` 做同镜像、同发布参数的对照：internal 网 vs 普通网桥，UDP 与 TCP 各一次。

## 证据

### 隔离最小拓扑矩阵（`code/topology_probe.py`）

|检查项|结果|说明|
|---|---|---|
|media 网络形状|`internal=true` `driver=bridge` `subnet=10.220.0.0/24`|与 t097 声明一致|
|宿主回环 UDP `127.0.0.1:30123`|`FAIL: timed out`|回包未收到|
|Stream→Gateway 同网 TCP `10.220.0.10:8005`|`true`|信令可达|
|Stream→其它 Profile 网 TCP `10.221.0.20:9000`|`false`|拓扑拒绝|
|Stream→宿主/LAN 服务网 TCP `10.222.0.20:9000`|`false`|拓扑拒绝|
|Stream→公网 IPv4 `1.1.1.1:443`|`false`|拓扑拒绝|
|Stream IPv6 地址|存在|`/proc/net/if_inet6` 非空|
|Stream→公网 IPv6 `2606:4700:4700::1111:443`|`false`|拓扑拒绝|
|Stream 网络归属|仅 `probe-s028-media`|无旁路网|
|Stream 端口发布|`30123/udp: null`|inspect 未生成宿主绑定|

### 对照实验（internal vs 普通网桥，同镜像同发布参数）

|拓扑|`docker port`|inspect `Ports`|宿主访问|
|---|---|---|---|
|internal + `-p 127.0.0.1:30201:30201/udp`|`no public port ... published`|`30201/udp: null`|超时|
|普通网桥 + `-p 127.0.0.1:30202:30202/udp`|`127.0.0.1:30202`|`[{HostIp:127.0.0.1,HostPort:30202}]`|收到 `ECHO:x`|
|internal + `-p 127.0.0.1:30301:8005/tcp`|`no public port ... published`|`8005/tcp: null`|连接失败|

结论：目标 Docker/OrbStack 对 internal 网桥上的容器**所有**已发布端口（TCP/UDP）均静默丢弃，与协议无关。生产 `start_stream_container` 正是把 Stream 仅挂该 internal 网并同时传 `ports=stream_ports()`（`docker_adapter.py:2462-2477`），因此宿主 Chrome 的媒体入口不成立。

## 结论

- 实测**不成立**：t097「internal 媒体网 + 宿主回环 UDP 发布」前提被证伪——internal 网放弃端口发布能力，媒体入口丢失。Gateway 信令、对公网/局域网/宿主其它服务/其它 Profile/IPv6 的拒绝矩阵由拓扑本身成立（这部分与 ADR 预期一致）。
- 触发 t097 ADR 回退条件：媒体网改回可路由 bridge 的同时，须以等价声明式手段恢复 Stream 出站拒绝（网络级出口 ACL），**不得**恢复 Stream Policy Agent 与命令式规则巡检。该回退改造尚未实施，登记 p164 跟踪；实施后须以本报告同法重验宿主回环 UDP 发布与拒绝矩阵。
- AC-004 当前判定：媒体观看/收听/操作在本机不成立；隔离矩阵成立。Verdict：SPIKE FAILED（发现阻断级拓扑缺陷）。
- 已验证事实入 `docs/findings/d054_orbstack_internal_network_drops_published_ports.md`。
- 决定：否（目标 OrbStack 的 internal 媒体网无法保留宿主回环端口发布）。
- 后续 task：t102，恢复普通媒体网桥的回环 UDP，并在网桥层保留完整出口拒绝。

### 复现

```bash
python3 docs/spikes/s028_t097_media_topology_orbstack/code/topology_probe.py
bash .scratch/s028_udp_diag.sh   # 对照实验（一次性诊断脚本，非正式 spike 资产）
```

探针资源全部以 `probe-s028*` 命名并在 `finally`/trap 清理，未触碰运行中 `cbrowser-*` / `cbrowsert100cold-*` 部署与 t100 worktree。
