---
pid: "p160"
slug: "t097_ac004_orbstack_media_isolation_verify"
status: "todo"
---
# p160 t097 AC-004 本地补验：OrbStack 真机媒体与 Stream 隔离矩阵

- 来源：t097 AC-004 [deploy] 的云端处置注记（云端无 Docker 与真实 Chrome，AC 已按用户裁定打勾、真实验证延期本地）
- 内容：目标 OrbStack 上，本机 Chrome 能观看、收听和操作同一个 Profile，媒体只从宿主回环入口接收；Stream 只使用约定的 Gateway 信令与本机媒体通道；隔离验证覆盖公网、局域网、宿主其它服务、Browser 与其它 Profile 的网络边界及有 IPv6 时的双栈行为；网络配置失配时不得把越界的 Stream 标记为可用。记录网络端点、运行资源身份与 Chrome 媒体结果。
- 处理：未开（留待本地 Mac 执行）
