# t103 立项契约审阅 · R1

**总评：FAIL。当前契约未通过，t103 暂不可开工。** 六个无效字段清理范围完整。`launch_args` 验收缺少迁移裁决与请求边界，运行中升级与回退缺少可执行定义，原生语言断言与实测存在差异。扩展替换有真实的 p165 依赖，其余清理可以独立交付。

审阅日期 2026-11-22。`6e60d20` 新增 task 与 progress，`12187d8` 登记 p165 并将 p166 以 `transferred`、`fix_ref: t103` 闭环。工作区 task 正文与 `6e60d20` 一致。以下判定针对 backlog 契约。 [t103 task](task.md) · [p166 原文和 Codex 评估](../../pending/p166_profile_advanced_options_noop_and_version_mismatch.md) · [p165](../../pending/p165_managed_extensions_and_bitwarden_passkey.md)

## 四项清理决策对照

|p166 决策|t103 落点|审阅结论|
|---|---|---|
|删除六个无效字段|范围、非范围、AC-001|已覆盖。涉及物理列、版本快照、克隆、探针、生成契约、字段分类、UI 和翻译。未来客户端拟人化与引擎升级留在范围外。|
|盘点后退役通用 `launch_args`|AC-002、AC-005|方向一致。实测有效的静音与语言行为已进入范围。迁移裁决、保留白名单时的拒绝形式、语言验收仍需明确。|
|扩展归 p165 的受管资产与显式权限|AC-003、AC-006|目标一致。当前缺前置资产能力，扩展迁移的身份保持与关闭、受管、自由三种模式仍缺确定契约。|
|完整前向迁移与真实引擎验收|AC-004 至 AC-006、测试策略、回退|已列出备份、平铺与包装快照、绑定、克隆和真机检查。原子性、实际升级行为和回退顺序需要补可验证判据。|

## 逐条验收审阅

### AC-001 · 通过

六个字段有充分证据支持移除。可以独立用升级后 SQLite 表结构与快照、创建和更新请求、公开与内部导出、指纹探针输出、前端字段分类及表单验收。验收请求应逐个提交已删除字段并断言 422 指向该字段，同时检查创建失败无新增 Profile、更新失败无配置版本或数据写入。新建后的手动「创建并启动」及按 `desired_state` 恢复仍有各自入口。范围中已排除客户端拟人化和未来高版本功能。 [t103 AC-001](task.md#%E9%AA%8C%E6%94%B6%E6%A0%87%E5%87%86) · [p166 核对与清理决策](../../pending/p166_profile_advanced_options_noop_and_version_mismatch.md#codex-%E8%AF%84%E4%BC%B0)

### AC-002 · 不通过 · t103_spec_f002（important）

- 当前范围已列出难映射输入，但 AC 用「按盘点裁决」概括，缺少阻断与可复核结果。为当前行和每个历史版本记录有效值及处置，至少区分冗余、等价映射、需裁决；对未解决项断言 DB 无 schema、行或快照改写。对带静音的当前行和历史快照验证迁入开启态，对无静音的旧版本和新建环境验证默认关闭。
- 语言夹具须分别覆盖显式 locale、`locale=null` 配合 GeoIP 开关、`--accept-lang` 多值、重复项以及超枚举项。p166 已验证的 SDK 规则是 GeoIP 提升取首个匹配，常规同键合并取末项。对 `AutomationControlled`，此前只观测 `navigator.webdriver` 一致，未知行为继续纳入裁决。
- 数据库盘点能发现存量配置。是否有外部脚本在未来才提交参数，还需用已知 API 消费方的证据或用户裁决确定，并记下最终分支。完全退役时，创建和更新传 `launch_args` 键应获 422。保留小白名单时，`launch_args` 键仍合法，已撤回的数组项应获 422，并验证合法含逗号值经实际表单保存、读取、再编辑后数组不变。 [t103 AC-002 与盘点策略](task.md#%E9%AA%8C%E6%94%B6%E6%A0%87%E5%87%86) · [p166 语言与迁移裁决](../../pending/p166_profile_advanced_options_noop_and_version_mismatch.md#codex-%E8%AF%84%E4%BC%B0) · [CloakBrowser 0.6.4 源码](https://github.com/CloakHQ/CloakBrowser/blob/v0.6.4/cloakbrowser/browser.py)

### AC-003 · 不通过 · t103_spec_f001、t103_spec_f005（important）

存量盘点和阻断原则正确。仍需给出受管资产接口与明确的匹配判据。扫描当前行和全部历史快照，区分空列表、可验证映射、缺失及歧义。对保留已加载行为的映射，应同时绑定版本化资产并设为允许，对无扩展的旧配置保留默认关闭。迁移阻断清单须指出 Profile 和版本，旧 `extension_paths` 键在创建、更新接口上须返回 422。

路径映射还会影响浏览器识别的扩展 ID。审阅时用固定 arm64 146 加载两份逐字相同、无 manifest `key` 的合成 MV3 扩展，只改目录，观察到不同的 `chrome.runtime.id`。因此仅映射到同名资产或相同内容无法保证既有扩展存储仍可访问。应区分受管资产 ID 与 Chromium 扩展 ID，通过受信标识与制品校验确认映射，验证迁移前后 Chromium ID 与合成扩展状态连续。无法保持时按未解决条目阻断，直到有人决定如何处置。 [t103 AC-003](task.md#%E9%AA%8C%E6%94%B6%E6%A0%87%E5%87%86) · [p165 受管资产设计](../../pending/p165_managed_extensions_and_bitwarden_passkey.md#L40) · [Chromium 扩展 ID 生成](https://chromium.googlesource.com/chromium/src/+/main/extensions/common/extension.cc) · [Chrome manifest key 文档](https://developer.chrome.com/docs/extensions/reference/manifest/key)

### AC-004 · 不通过 · t103_spec_f003（important）

- **迁移原子性和幂等。** 以旧 release 的真实 schema stamp 构造升级库，覆盖平铺/包装快照及损坏或无法映射的数据，校验版本记录标识、绑定版本和 `proxy_credential_revision`。分别验证发现阻断项后零业务写入，以及已经开始执行 DDL/DML 后故障时 schema、行、快照和 Alembic stamp 一并回退。当前 SQLite Alembic 默认 `transactional_ddl=False`。已有 `context.begin_transaction()` 与 fail-before-write 只提供部分证据。再次 `upgrade head` 时 Alembic 会因 stamp 跳过已执行 revision，应对比升级后的 DB 状态，并独立测试盘点/变换重算无漂移。 [Alembic 环境](../../../src/backend/migrations/env.py#L38) · [快照修复契约](../../specs/storage_and_artifacts.md#L88)
- **在跑环境与版本选择。** 当前部署契约允许保留运行中的 Browser，Supervisor 收到新启动请求时按指定版本读快照并写 `snapshot.json`，协调器的常规启动目标是最新配置。现规范把原实例接管与新实例创建合写为「在跑环境升级、重启成功」。应明确旧实例继续运行或重建的选择，明确由谁在何时生成新快照，以及在哪个场景启动历史绑定版本、在哪个场景按正常语义采用当前版本。用绑定 `N`、当前 `N+1` 的不同配置对照，验收升级接管、首次新实例、历史版本读取、仅配置/含状态克隆，同时核对运行意愿和绑定。真实 release 升级、接管与回退应单列 `[deploy]` 或纳入明确的部署 AC。 [release 升级契约](../../specs/release_deployment.md#L30) · [Supervisor 指定版本读取](../../../src/backend/cbrowser/supervisor/control_server.py#L218) · [协调器版本选择](../../../src/backend/cbrowser/api/runtime_coordinator.py#L1265)
- **回退顺序。** `deploy.sh rollback` 要求目标版本的 migration head 等于在线 DB stamp，因此跨本次 revision 时直接回退会被拒绝。隔离演练应先停止新版写入并恢复迁移前数据库，再按匹配的 release 与 compose 制品启动旧版、确认旧 stamp 和 Profile 可用。若选用环境级恢复点，其创建要求 Profile 无写者，恢复还有 stamp 一致门禁。运行中升级场景应明确在线 DB backup 与完整环境恢复点各自的用途。 [rollback stamp 门禁](../../../scripts/deploy.sh#L1199) · [数据库恢复命令](../../../scripts/deploy.sh#L1275) · [环境恢复点](../../specs/release_deployment.md#%E7%8E%AF%E5%A2%83%E6%81%A2%E5%A4%8D%E7%82%B9t066)

### AC-005 · 不通过 · t103_spec_f004（important）

- **语言。** 原评估要求对原生语言、HTTP、JS 分别验证，尚未证明现有 146 原生界面随 locale 改变。审阅补测使用原镜像 `dcb33194200f`、固定 arm64 `146.0.7680.177.3`、SDK `0.6.4`、断网 Xvfb、全新临时 Profile，显式传入 `en-US` / `zh-CN` 并关闭 GeoIP。HTTP 分别为 `en-US,en;q=0.9` / `zh-CN,zh;q=0.9`，`navigator.languages` 分别为 `["en-US"]` / `["zh-CN"]`，两组 `chrome://settings` 和 `chrome://version` 的标题均为英文。该探针覆盖内置界面，完整桌面菜单和 Selkies 路径仍待部署验收。建议以 Web 主语言与有序回退规则作为现有行为断言，同时记录原生界面边界。若确需原生本地化，应作为新增产品契约，先验证固定镜像资源、启动时选取方式和可观察控件，再加入门禁。
- **恢复会话。** 当前标为待实验的实际是产品裁决，固定 146 已证实关态可受原生偏好支配。建议保留当前行为并更新中英文帮助，明确关态遵循 Chromium 原生启动偏好。若选择强制关闭恢复，应明确持久偏好会否被覆盖、重新打开是否恢复原偏好。两条路径都要验证 Profile 开/关 × 原生恢复开/关的四格。测试应以已有两个带标记的标签为观察对象。
- **静音。** 该项判据可测。正式验收沿用同一确定音源和同一音频监测端做开关正负对照，覆盖迁移得到的开启态和默认关闭。 [t103 AC-005](task.md#%E9%AA%8C%E6%94%B6%E6%A0%87%E5%87%86) · [p166 固定引擎观察](../../pending/p166_profile_advanced_options_noop_and_version_mismatch.md#codex-%E8%AF%84%E4%BC%B0)

### AC-006 · 不通过 · t103_spec_f001、t103_spec_f005（important）

四个核心场景和真实有头引擎要求正确。受管模式需实际证明同一 Profile 可同时运行两项选中扩展，并拒绝曾在自由模式安装的未选中扩展。关闭态要用已经安装过扩展的 Profile 观察内容脚本或后台行为确实消失，同时核对无显式加载路径。隔离态需验证未绑定资产在另一 Profile 与 Stream 容器不可见，扩展运行态的本地数据不串用。自由模式应写清安装入口和验收结果，例如经受支持入口安装合成扩展、执行并重启持久。若三个候选入口均不可用，先由 p165 决定保留何种入口或暂只交付受管模式。固定内核能加载合成 MV3 的实测不能证明自由安装或 Bitwarden 已通过。p165 自身的 Passkey 与代理出口验收应由其实现 task 承接。 [t103 AC-006](task.md#%E9%AA%8C%E6%94%B6%E6%A0%87%E5%87%86) · [p165 运行模式及实施前验证](../../pending/p165_managed_extensions_and_bitwarden_passkey.md)

## p165 依赖裁决 · t103_spec_f001

[progress.md](progress.md#L5) 当前为 backlog，`depends_on` 为空。`task.py effective-status` 确认有效来源为 main，`preflight t103 --creation` 通过并带警告，`preflight t103 --allow-backlog` 因一项 `UNVERIFIED-BLOCKING` 失败。该标记准确反映**现有整包范围**无法交付，但团队已知缺口属于本仓尚未实现的产物。用明确的 task 交付边界和硬依赖表达更准确。`start` 会校验 `depends_on` 的前置为 done，并核对实际基座包含前置实现。仅立项或登记编号不足以满足。 [任务启动门禁](../../../.repo_template/scripts/repo_task/integration.py#L183)

1. **推荐拆分范围，t103 先做独立清理。** t103 承接 AC-001、AC-002、修订后的 AC-004/005，以及相应迁移、文档和部署验证。AC-003/006 连同 `extension_paths` 的盘点、替换、扩展相关迁移与自由模式实验转给 p165 实现 task，整项能力由同一 task 完成。t103 保留当前 `extension_paths` 契约供 p165 原子替换。拆分后可移除 t103 的扩展阻塞，独立完成六字段清理与参数盘点。两项都触及 Profile 表、领域模型、Runner 与 Alembic head，按串行实施协调，若并行排期才登记文件冲突。明确 t103 对 `--disable-extensions` 的归并建立在当前默认集上，p165 另验收新的权限策略。将拆分后的 p165 task 写回来源追踪，保持 p166 的扩展结论有明确承接。
2. **若 t103 必须一次交付全部现有 AC，先立窄范围 p165 前置 task。** 前置只交付可独立验证的资产导入/验证、不可变标识、目录解析及容器只读挂载契约，并定义支持迁移的旧路径映射资料。t103 负责 Profile 权限、字段替换和扩展端到端验收。Bitwarden 本体和完整资产管理 UI 可后续交付。明确接口后由调度工具登记真实前置 tid，按 `depends_on` 阻止提前开工。将占位的 `UNVERIFIED-BLOCKING` 改写为可核查的产物契约和依赖引用，仍无法确定的外部条件保留阻塞。若先实施的 p165 已完整替换 `extension_paths`，则由它独立持有这两条 AC，t103 只引用交付。
3. **若要合并实施，先明确授权与范围。** 在同一个 task 写明资产交付、Profile 迁移、回退与真机验收。合并后由该 task 自己交付的项目产物无须登记为外部前置依赖。当前 `非范围` 与 `依赖与约束` 两处给出的「协同」不足以确定实际交付边界。仅将标记降为 `UNVERIFIED-SPIKE` 或加 mock 资产无法满足现有 AC-003/006。

## 引用核验 · t103_spec_f006（minor）

- p166 `原文` 的 16/22、无条件覆盖 `--lang` 及尚未实测 flag 等陈述，已经被同文评估更新。t103 采用 17/22、条件优先级及固定 arm64 实测，引用属实。`auto_launch` 已有明确说明且确实无启动消费。建议把「触发待应用」收紧为修改后生成版本，运行绑定落后时显示待应用。`chrome://version` 显示四段版本，制品第五段由仓内 pin 和摘要确认。三个 flag 的最低引擎版本与锁定 SDK 文档一致，结论限已测 arm64 与场景。 [p166](../../pending/p166_profile_advanced_options_noop_and_version_mismatch.md) · [CloakBrowser 0.6.4 参数表](https://github.com/CloakHQ/CloakBrowser/blob/v0.6.4/README.md#additional-flags) · [Playwright 1.64.1 默认值](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/src/server/chromium/chromiumSwitches.ts)
- 当前 `0013_profile_identity.py` 确实有 fail-before-write 并调用已修正的快照 helper。历史发布过的 0013 只处理顶层，包装快照的补偿来自 t089 的 `0014_repair_wrapped_snapshots.py`。引用应补 0014 与共享实现，避免把当前 helper 行为归于原版 0013。单一 head、前向迁移和快照规则以 `storage_and_artifacts.md` 为直接证据。`conventions.md` 支持生成契约和 MountPlanner 约定。 [0013](../../../src/backend/migrations/versions/0013_profile_identity.py#L109) · [0014](../../../src/backend/migrations/versions/0014_repair_wrapped_snapshots.py#L1) · [快照 helper](../../../src/backend/cbrowser/adapters/database/snapshot_identity.py#L116) · [项目约定](../../blueprint/conventions.md)
- `profile_management`、`fingerprint_platform`、`storage_and_artifacts`、`browser_isolation`、`ui_design_system` 五份 spec 均存在且 active。按最终范围同步有实际契约变化者。Finalization 还应检查 `blueprint/architecture.md` 与 `blueprint/security.md` 的现行 `launch_args` 严格加载段落，若字段退役则同步更新，避免长文继续承诺已删除的能力。若采用影响发布流程的升级或回退新语义，同步 `release_deployment.md`。 [架构第 5.5 节](../../blueprint/architecture.md#L176) · [安全契约](../../blueprint/security.md#L162) · [发布部署](../../specs/release_deployment.md)

本轮仅复核 backlog 文档并运行只读预检与断网引擎探针。未按 t103 实施验收，未盘点线上数据库。
