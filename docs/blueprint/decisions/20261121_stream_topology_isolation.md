# 041 Stream 隔离收归媒体网络拓扑：Policy Agent 只服务 Browser（2026-11-21，t097）

- 背景：ADR 039 后 Browser 与 Stream 共用一个双角色策略模型，各启动一个常驻 Policy Agent 在目标 netns 内安装、巡检与修复规则。Stream 的可达范围其实只有三样：同 Profile 媒体通道、Gateway 固定端点信令、宿主回环 UDP 发布——这组范围恰好是一个 per-Profile 受管网络的成员关系本身。继续为 Stream 保留 Agent，等于为「本可由拓扑声明的事实」保留一套安装、漂移判定与失败处置面：启动被策略就绪 gate 阻塞、稳态每轮 verify、不可确认走替换、Agent 容器与 Browser 同量级 churn。Stream 规则中「允许链路本地媒体回包」一条还是拓扑等价性的未证项（见下「验证与回退」）。
- 选项：
    1. 维持双角色 Agent，仅降低 Stream verify 频率：gate 阻塞、漂移处置与 churn 仍在，且低频 verify 拉长暴露窗口。
    2. Stream 只装一次规则、不再巡检：规则仍是命令式状态，漂移无观测且与拓扑事实双写，迟早不一致。
    3. Stream 隔离收归拓扑（本 ADR 采用）：per-Profile 媒体网络设为 internal，单一受管拓扑承载本机媒体与 Gateway 信令；Stream 不设 Agent、gate 与规则集，Supervisor 稳态不再巡检、修复或接管 Stream 策略。
- 结论：采用选项 3。
    - **拓扑**：媒体网络在既有固定端点规格（t026、d029）之上增加 internal 属性，合规判定同时要求计划标签、IPAM 与 Internal 三者；存量可路由网络按不合规经既有 Stream-only 重建路径一次性收敛。Stream 的 UDP mux 仍只发布宿主回环 `127.0.0.1`（ADR 031/t054 的仅回环口径不变）。Stream 容器以镜像自有 ENTRYPOINT 直接启动，不再等待任何策略就绪标记。
    - **Browser-only Agent**：Policy Agent 只为 Browser 保留（ADR 039 的形态、协议与围栏不变，ADR 038 的代理封闭口径不变）；协议与策略模型的 role 收敛为 browser-only。Agent 容器改名 `<prefix>-<NNNN>-policy-agent` 并与沙箱同属 `<prefix>-profiles` 分组（service `<NNNN>-policy-agent`、标签含展示编号），与 ADR 040（t083）的 Supervisor 部署身份/接管口径一致：归属与接管仍只认 deployment/profile/instance/config version/目标容器标签全等，分组与名称只用于呈现和形状判定。
    - **收敛**：Supervisor 启动的孤儿收敛一次性处理存量旧形状——绑定 Stream 的 Agent 一律经完整身份校验后删除；绑定存活 Browser 且身份全等的旧形状 Agent（旧哈希槽名、无分组标签）由 ensure 路径就地替换为现行形状，保证升级后每个 Browser 至多一个现行 Agent、无旧 Agent 残留。Stream-only 替换的触发面收窄为媒体网络不合规与可修复的未注册；策略不可确认的 30 秒预算与暂停隔离只适用于 Browser。
    - **验证与回退**：声明式拓扑的真机等价性（宿主回环 UDP 发布在 internal 网络上的可达与回包、Gateway 信令、公网/局域网/宿主服务/跨 Profile 拒绝矩阵、IPv6 双栈）由 p159 的隔离最小拓扑 spike 实测，部署级媒体与升级/回退验证见 p160/p161。若 spike 证明回环发布与 internal 不等价，回退条件为：媒体网络改回可路由 bridge 的同时，必须以等价的声明式手段恢复 Stream 出站拒绝（例如网络级出口 ACL），不得恢复 Stream Policy Agent 与命令式规则巡检。
