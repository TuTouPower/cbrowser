# Task spec

## 背景

`cbrowser` 采用“宿主机 Chrome 经 Selkies WebRTC 查看远端隔离 Docker 容器内 CloakBrowser”的架构。由于 WebAuthn 在浏览器内核层严格绑定来源域名与 `rpId`，且隔离容器不接入宿主机平台认证器（Touch ID / iCloud 钥匙串）、蓝牙（BLE）或 USB/FIDO HID 设备，宿主机 Chrome 中的 Bitwarden 扩展无法向容器内网页提供 Passkey。2026-11-22 在纯英文美国代理测试环境 `0088` 上实测确认：远端引擎为 `ungoogled-chromium 146.0.7680.177` 且命令行被 Playwright 默认注入 `--disable-extensions`，`chrome://extensions` 为空且 Chrome Web Store 安装按钮不可用；此外无 manifest `key` 的相同 MV3 扩展在不同挂载目录下会派生不同 `chrome.runtime.id`，导致仅按同名或内容映射无法保证既有扩展存储连续。

依据 `p165` 已采纳的方案一与 `t103` R1 审阅裁决（承接原 `t103` 移出的 `AC-003`、`AC-006`、`extension_paths` 盘点/替换/迁移及自由模式实验），本 task 建立受管扩展资产体系与显式扩展权限，替换原始 `extension_paths` 字段，并最终在隔离容器内跑通 Bitwarden 扩展 Passkey。

## 契约区

### 范围

- **受管扩展资产库与管理接口**（参照本仓 `font_sets` 与 `MountPlanner` 受管存储契约）：
    - 控制面提供扩展包上传/导入（`.zip` / `.crx`）、解包校验、列表查询与删除/引用保护接口；校验 `manifest.json` 合法性、提取不可变受管资产 ID、名称、版本、图标元数据，并校验或保存 Chromium 扩展身份依据（如 manifest `key` 与制品完整性信息）；
    - 受管扩展资产统一存于受管存储卷，纳入环境恢复点（`restore_point`）与迁移盘点视野，禁止宿主任意路径直接进入容器创建参数。
- **显式扩展权限开关与受管 ID 替换 `extension_paths`**：
    - 在 Profile 运行配置与表单引入 `allow_extensions: bool = False`（默认关闭）及受管扩展 ID 列表（`extension_ids`，支持多选、排序与增删多个扩展），替换原始 `extension_paths` 字段；提交旧 `extension_paths` 键在创建与更新接口按严格 DTO 返回 422；
    - 界面默认关闭并隐藏/禁用扩展选择；勾选「允许扩展」后支持多选受管扩展（受管模式）或留空进入自由模式，并显式提示开启扩展对指纹特征面及跨多环境同主账号密码库本地缓存的隐私风险。
- **存量 `extension_paths` 盘点、Chromium 扩展 ID 连续性与前向迁移**：
    - 迁移前扫描 `profiles` 当前行及全部 `profile_config_versions` 快照的 `extension_paths`，精确区分：`空列表`、`可验证映射`、`缺失` 与 `歧义`；
    - 空列表直接迁为 `allow_extensions=false`、`extension_ids=[]`；可验证映射须通过受信标识与制品校验确认对应受管资产，**且校验迁移前后浏览器内 `chrome.runtime.id` 与扩展本地存储连续性**，同步绑定版本化受管资产并置 `allow_extensions=true`；
    - 缺失、歧义或**无法保持 Chromium 扩展 ID 连续性**的非空条目，输出明确指名 Profile 与版本的阻断清单并 fail-before-write 零写入中止升级，禁止无声丢失已加载扩展或静默更换扩展 ID；
    - 新增前向 Alembic revision，先以可恢复备份演练，沿用 `0013_profile_identity.py`、`0014_repair_wrapped_snapshots.py` 与 `snapshot_identity.py` 模式原子迁移平铺及包装快照并保留版本号、运行绑定、代理凭据修订号与用户数据。
- **Supervisor 只读挂载与 Runner 扩展模式控制**：
    - Supervisor `MountPlanner` 仅将启用扩展且选中的受管扩展目录以 `:ro` 只读挂载进目标 Browser 容器（未启用 Profile 与 Stream 容器不可见）；
    - `runtime_agent/runner.py` 显式接管扩展启动默认参数（不再受 `cloakbrowser` 硬编码 `IGNORE_DEFAULT_ARGS` 限制）：
        1. **关闭态（`allow_extensions=false`）**：保持禁用扩展系统（`--disable-extensions`）且不传递任何显式加载路径，确保此前装过扩展的持久化 Profile 也不再执行任何扩展；
        2. **受管开启态（`allow_extensions=true` 且选定受管 ID）**：移除 `--disable-extensions`，仅传递选中扩展对应容器只读目录至 `--load-extension` 与 `--disable-extensions-except`，拒绝加载自由安装的未选中扩展；
        3. **自由模式（`allow_extensions=true` 且选中列表为空）**：先经前置 spike 裁决固定 `146.0.7680.177.3`（`ungoogled-chromium`）受支持的安装入口；开启时既不传 `--disable-extensions` 也不传 `--disable-extensions-except`，允许用户在已定入口安装/加载扩展并持久化于本 Profile `user_data_dir`。
- **容器内 Bitwarden 扩展 Passkey 端到端验证**：在固定目标引擎有头容器与代理环境下验证受管模式加载 Bitwarden 官方扩展、代理出站不泄露且完成 WebAuthn Passkey 注册与登录；同步更新相关 spec、blueprint 与自动化测试。

### 非范围

- 宿主机 Chrome 扩展跨 WebRTC 透传、控制台自身 Passkey 登录、cbrowser 原生 `WebAuthn` 虚拟认证器（`p165` 方案二）及物理安全密钥 CTAP2 桥接（`p165` 方案三）。
- Profile 六个无效字段删除及通用 `launch_args` 盘点退役（由前置依赖 `t103` 独立交付）。
- Alembic downgrade（仅向前迁移）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：控制面提供受管扩展资产导入/上传、合法性校验、列表查询与引用保护接口：合法扩展包生成不可变受管资产 ID 并保留名称、版本、图标与扩展身份校验信息；损坏压缩包、缺失或非法 `manifest.json`、无法确定稳定扩展标识的包或仍被环境/绑定版本引用的资产删除均在 API 边界明确拒绝。
- [ ] AC-002：Profile 运行配置与 API 由 `allow_extensions`（默认关闭）及受管扩展 ID 列表替换原始 `extension_paths`；关闭态既禁用扩展系统也不传递显式加载路径；迁移前扫描 `profiles` 当前行及全部历史快照的 `extension_paths`，精确区分空列表、可验证映射、缺失与歧义，可验证映射须经受信标识与制品校验同时绑定版本化资产、设为允许且保持迁移前后 Chromium 扩展 ID（`chrome.runtime.id`）与合成扩展本地存储状态连续；缺失、歧义或无法保持 Chromium 扩展 ID 连续性的条目指名 Profile 与版本 fail-before-write 阻断（零业务写入）；前向迁移支持平铺与包装快照并保持幂等，旧 `extension_paths` 键在创建或更新接口返回 422 校验错误。
- [ ] AC-003：新建与编辑表单默认隐藏或禁用扩展选择器，勾选「允许扩展」后支持多选、增删多个受管扩展（不暴露按逗号切分的自由文本路径）并展示开启扩展的指纹与跨环境凭证缓存风险提示；配置保存、回显、待应用提示及 OpenAPI/前端生成类型与 `profile_field_classification.ts` 完全同步。
- [ ] [deploy] AC-004：在固定目标浏览器引擎的真实有头容器拓扑中验证扩展四态与自由模式：1）默认关闭态不加载扩展；2）受管模式同一 Profile 可同时加载并运行两项选中受管扩展，并拒绝曾在自由模式安装的未选中扩展；3）用已安装过扩展的持久化 Profile 切回关闭态重启后，原有扩展内容脚本与后台行为确实不再执行且启动命令无显式加载路径；4）两个 Profile 相互隔离（未绑定资产在另一 Profile 与 Stream 容器均不可见，扩展运行态本地存储不串用）；5）按前置实验裁决的自由模式受支持入口验证安装合成扩展、执行并重启持久化。
- [ ] [deploy] AC-005：在固定目标浏览器引擎的真实有头容器与代理链路下通过受管模式加载 Bitwarden 官方扩展，验证扩展在浏览器代理链路下登录同步（不绕过代理直连），并成功完成 WebAuthn Passkey 注册（`navigator.credentials.create`）与 Passkey 登录（`navigator.credentials.get`）流程。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001 至 AC-003 可通过前后端单元测试、OpenAPI/类型导出门禁、迁移阻断与连续性测试及 API/Supervisor 挂载集成测试自动验证。
- `[deploy]` AC-004 与 `[deploy]` AC-005 须在本地 OrbStack 真实 Docker、固定有头目标引擎与真实/受控 WebAuthn 站点环境下执行并留证，不得以 mock 或仅检查命令行参数代替。

## 上下文区

- 关联 spec：docs/specs/profile_management.md
- 受影响 spec：`docs/specs/browser_isolation.md`、`docs/specs/storage_and_artifacts.md`、`docs/specs/ui_design_system.md`、`docs/specs/release_deployment.md`
- 来源：`p165`（2026-11-22 方案一立项，含测试环境 `0088` 实测证据）与 `p166` / `t103` `review_r1.md`（承接由 `t103` 拆分移出的原 `AC-003`、`AC-006`、`extension_paths` 盘点替换与扩展连续性迁移以及自由模式实验）。

### 有意不测

- 跨机器迁移扩展状态、宿主机浏览器扩展跨 WebRTC 桥接、控制台自身 Passkey 登录及原 `p165` 备选方案二/三。

### 测试策略

- **受管资产与迁移连续性测试**：构造含与不含 manifest `key` 的合成 MV3 扩展包测试资产校验与稳定 ID 映射；在隔离 SQLite 库覆盖空列表、可验证映射（断言迁移前后 `chrome.runtime.id` 与扩展本地存储数据一致）、缺失、歧义、无法保持扩展 ID 连续性阻断（零写入）、平铺/包装快照与重启幂等；校验旧 `extension_paths` 键 422 拒绝。
- **挂载与隔离单测/集成测试**：断言 `MountPlanner` 在关闭态零扩展挂载、开启态仅对绑定 Profile 只读挂载所选扩展且 Stream 容器零挂载。
- **真实引擎多扩展与 Bitwarden Passkey 验收**：先通过前置 spike 确定固定 `146` 引擎自由模式实际安装入口及有无 `key` 扩展 ID 连续性；随后在有头容器中依次实测默认关闭、双受管扩展并行且拒绝未选扩展、已装扩展 Profile 切回关闭态失效、双 Profile 存储隔离、自由模式安装重启持久化，以及代理环境下 Bitwarden Passkey 注册/登录。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 自由模式下固定 `146.0.7680.177.3`（`ungoogled-chromium`）的实际扩展安装入口（Chrome Web Store / 本地 `.crx` 拖入 / 开发者模式加载解压目录）：`UNVERIFIED-SPIKE`，在实施自由模式前于去掉 `--disable-extensions` 的隔离有头容器中逐项实测三个候选入口并先定结论；若三者均不可用，先裁决保留方案或暂只交付受管模式。
- 固定 `146` 引擎在移除 `--disable-extensions` 后加载多扩展（含带/不带 manifest `key` 的 ID 稳定性及 Bitwarden 官方扩展）与代理环境下 `navigator.credentials.create/get` 链路兼容性：`UNVERIFIED-SPIKE`，在临时隔离容器中先用双合成 MV3 扩展与 Bitwarden 扩展实测验证后回填结论再冻结实现。

### 风险与回退

- 风险：旧 `extension_paths` 若缺稳定 manifest `key` 或原路径不可还原至同一扩展 ID，直接替换会导致扩展 `chrome.runtime.id` 改变并丢失既有本地数据（含 Bitwarden 本地状态）；自由模式若未受控可能让 `chrome://extensions` 残留未选扩展在受管模式继续运行；开启扩展本身增加指纹面。
- 回退：迁移前完成数据库在线备份与可恢复演练，遇到缺失、歧义或无法保持扩展 ID 连续性立即 fail-before-write 阻断；发现发布后扩展状态或隔离回归时停写恢复旧库并回退至匹配的旧 release，保留原扩展存储目录不破坏用户数据。

### 依赖与约束

- 硬依赖 `t103`（`depends_on: t103`）：共享 `profiles` 表、领域模型、`runner.py` 与 Alembic head，按串行调度在 `t103` 完成六字段清理与 `launch_args` 退役之后执行本 task。
- 严格遵循 `AGENTS.md` 开发铁律（零兼容性负担）与 `docs/blueprint/conventions.md`（受管存储卷由 `MountPlanner` 构造、迁移只向前、fail-before-write、Alembic 单一 head）。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：更新受管扩展资产存储与 Browser 只读挂载边界。
- `docs/blueprint/domain.md`：记录 `allow_extensions`、`extension_ids` 与替代 `extension_paths` 的运行配置与迁移连续性规则。
- `docs/blueprint/browser_runtime.md`：记录 Runner 扩展四态参数控制、自由模式支持边界及自由安装与受管白名单关系。
- `docs/blueprint/persistence.md`：更新受管扩展资产表/`profiles` 字段及前向迁移说明。
- `docs/blueprint/security.md`：记录扩展包校验、跨 Profile 与 Stream 只读隔离边界及 `extension_paths` 422 拒绝。
- `docs/blueprint/testing.md`：补充扩展 ID 连续性迁移、四态隔离与 Bitwarden Passkey 真机验收门禁。
