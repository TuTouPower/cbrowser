# Task spec

## 背景

t097 的 internal 媒体网在 OrbStack 上不发布宿主回环端口，Stream 仍可注册但 Viewer 收不到媒体。解除 internal 前须在网络层保留 Stream 对其它出口的拒绝。旧版升级与回退仍缺隔离实例的完整证据。

## 契约区

### 范围

- 恢复宿主回环媒体并保持 Stream 网络出口隔离；验证从旧版两类 Policy Agent 升级及回退时的真实媒体、配对、数据和归属行为。

### 非范围

- 实际生产实例升级、对外发布、修改宿主 OrbStack 或 Docker CLI 全局代理设置。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] [deploy] AC-001：正式拓扑下，宿主仅通过回环 UDP 发布与 Stream 互通，Chrome Viewer 收到动态媒体并可操作。Stream 能连接本 Profile Gateway 信令。正常 Stream 没有对应 Policy Agent。
- [x] [deploy] AC-002：Stream 拒绝连接公网、局域网、宿主服务（含 FlClash）、其它 Profile 与 Browser 的其它网络；IPv6 无出站。出口隔离不可用时 Stream 无法启动。未绑定代理的 Browser 与已绑定代理的 Browser 保持既有隔离和出口选择。
- [x] [deploy] AC-003：隔离实例从两类 Policy Agent 拓扑升级后保留 Profile 数据与运行意愿，收敛到每 Browser 一个 Agent 的形状并恢复媒体。回退到支持的上一 release 后旧版媒体与代理路径可用，另一部署资源归属与运行状态保持。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

AC-001–003 由实际 OrbStack Docker 与 Chrome 验证。纯逻辑、失败封闭与迁移条件用自动化测试覆盖。

## 上下文区

- 关联 spec：docs/specs/browser_isolation.md
- 关联 spec：docs/specs/webrtc_remote_display.md
- 关联 spec：docs/specs/release_deployment.md
- 来源：p164、p161；t097 / s028 / d054 已验证 internal 网桥丢弃发布端口。2026-11-21 在目标 OrbStack 用独立网桥确认正常网桥发布回环 UDP，内核规则可同时保留 Gateway 信令、允许回包和拒绝桥上宿主服务。

### 有意不测

- 公开发布及生产实例变更不在范围内。验收使用隔离部署与权限兼容的旧版镜像。

### 测试策略

- 测试前置规则拒绝失败、网络形状与运行收敛；实际验收对比受限出口与同目标可达基线，检查 UDP、Gateway、Chrome Viewer、升级和回退。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 已在目标 OrbStack 验证 host 网络辅助容器可安装精确作用于专属媒体网桥和 Stream 地址的内核过滤。从同一 Stream 端点验证 host INPUT、转发回复和同网 Gateway，完整目标矩阵仍列入 AC-002。

### 风险与回退

- 风险：桥发布、规则未能生效、宿主代理路径旁路、旧 Stream 或 Agent 收敛不完整。
- 回退：保留旧有效 release 与 Profile 数据。对不满足出口限制的 Stream 失败封闭，使用隔离实例验收后再考虑生产部署。

### 依赖与约束

- 媒体 UDP 仅发布宿主回环；Browser 的 Agent 和显式代理配置继续按 t097 保留。使用现有 OrbStack 网络代理关闭、Docker Hub 镜像加速与 Docker CLI 拉包代理设置，引擎显式代理只给下载辅助容器。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：媒体网发布与出口限制。
- `docs/blueprint/decisions/20261121_stream_topology_isolation.md`：记录触发回退后的约束与证据。
