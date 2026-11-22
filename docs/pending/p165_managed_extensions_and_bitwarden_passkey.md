---
pid: "p165"
slug: "managed_extensions_and_bitwarden_passkey"
status: "todo"
---
# p165 支持受控多扩展与容器内 Bitwarden Passkey（方案一）

- 来源：用户提出（2026-11-22）。用户希望在 cbrowser 隐私浏览器中使用 Bitwarden 等外部账号提供的 Passkey（并提出“默认不允许扩展，勾选允许扩展后在下方配置多个扩展”的产品结构），在对比全部可行方案后明确选定**方案一**并要求沉淀完整分析与设计方案。
- 内容：

## 一、核心问题分析（为什么当前用不了 Bitwarden Passkey）

1. **宿主机 Chrome 扩展无法跨端作用于远端容器网页（结构性隔离）**
    - 宿主机 Google Chrome 访问管理页会话时，只通过 `<iframe src="/selkies/index.html?profileId=...">`（`src/frontend/src/features/browser-session/SessionPage.tsx:219-228`）接收 Selkies WebRTC 音视频流，并转发键鼠与剪贴板（`allow="autoplay; fullscreen; clipboard-read; clipboard-write"`）。
    - 真正打开目标站点并调用 WebAuthn（`navigator.credentials.create()` / `navigator.credentials.get()`）的浏览器运行在隔离的 Docker 容器 `browser-runtime-{profileId}` 内。
    - WebAuthn 协议在浏览器内核层强制绑定来源域名与 `rpId`，宿主机网页/扩展既看不到容器内页面的 DOM 与 Origin，也不能由本地控制台地址替任意外部域名代签；同时 Browser 容器以 `read_only=True`、`cap_drop=["ALL"]`、`no-new-privileges` 运行（`src/backend/cbrowser/supervisor/docker_adapter.py:2324-2355`、`src/backend/cbrowser/supervisor/volume_spec.py:60-89`），未接入宿主机 Touch ID 平台认证器、BLE 蓝牙或 USB/FIDO HID 设备，也不存在宿主机扩展桥接通道。
    - 另确认管理台自身登录（`src/frontend/src/features/auth/LoginPage.tsx`、`src/backend/cbrowser/api/v1/auth_router.py:62-112`）仅支持管理员密码，无 Passkey 登录。
2. **远端容器内测试实证：Chrome 扩展系统在默认配置下被彻底禁用**
    - 2026-11-22 新建纯英文美国代理测试环境 `0088`（ID `c9a0f33a-941a-44a6-9c62-5bbc807c275e`，名称 `US-EN-Bitwarden-Test`，代理 `🇺🇸 美国标准 IEPL 专线 1` / Los Angeles / `586ms`，`locale=en-US`，`include_cjk_fonts=False`，`geoip=True`），启动至 `running` 后经受控 CDP 自动化通道实测：
        - `chrome://version`：内核为 `Chromium 146.0.7680.177 (Official Build, ungoogled-chromium) (64-bit)`，命令行携带 **`--disable-extensions`**；
        - `chrome://extensions`：页面内容为空，无法使用；
        - Chrome 应用商店 Bitwarden 页面（`nngceckbapebfimnlniiiahkandclblb`）：顶部提示 `Switch to Chrome to install extensions and themes`，**`Add to Chrome` 按钮处于 `disabled: true` 状态**。
3. **现行 `extension_paths` 链路的机制断裂**
    - **默认强制禁用扩展**：`src/backend/cbrowser/runtime_agent/runner.py:702-717` 通过 `cloakbrowser.launch_persistent_context_async(...)` 拉起浏览器；`cloakbrowser`（`.venv` 中 `cloakbrowser/config.py` 与 `browser.py:695-703`）向 Playwright 传递的 `ignore_default_args` 仅包含 `["--enable-automation", "--enable-unsafe-swiftshader"]`，导致 Playwright 1.64.1 的默认 `chromiumSwitches`（`playwright/driver/package/lib/coreBundle.js`）无条件注入 `--disable-extensions` 与 `--disable-component-extensions-with-background-pages`。`src/backend/cbrowser/launch_args.py` 白名单也不支持移除默认参数。
    - **参数冲突与容器挂载断层**：`ProfileConfig.extension_paths`（`src/backend/cbrowser/domain/models.py:278`）虽然存在且会由 `cloakbrowser.build_args`（`browser.py:1488-1495`）转成 `--load-extension=...` 和 `--disable-extensions-except=...`，但：
        1. 并未把 Playwright 默认注入的 `--disable-extensions` 摘除；
        2. Supervisor 容器挂载（`src/backend/cbrowser/supervisor/volume_spec.py:60-89`）只挂了 Profile 数据、文件交换区、字体集与运行目录，宿主机目录完全不进容器，UI 填写宿主机路径必然不可达；
        3. 前端表单（`src/frontend/src/features/profiles/ProfileForm.tsx:873-888`）仅为单个按 `,` 分割的文本输入框，多扩展交互脆弱；
        4. 当前引擎为 `ungoogled-chromium`，即使解除 `--disable-extensions`，其商店在线一键安装接口通常仍受限，必须有离线包/扩展库加载链路。

## 二、Passkey 解决方案对比与选型结论

|方案|原理与能否复用现有 Bitwarden Passkey|跨环境隔离与反指纹|采纳结论|
|---|---|---|---|
|**方案一：容器内受控多扩展加载 + Bitwarden 扩展**|Bitwarden 扩展通过内容脚本拦截网页 `navigator.credentials.create/get`，使用云同步密码库私钥在扩展内部完成 WebAuthn 签名，**不依赖硬件/蓝牙/Touch ID**，可直接复用现有 Bitwarden Passkey|同一 Bitwarden 主账号登录多环境会缓存密码库且引入扩展特征；可用子账号/Vaultwarden 缓解|**已采纳（优先落地）**|
|**方案二：cbrowser 原生 Passkey 钥匙串 + CDP `WebAuthn` 虚拟认证器**|控制台加密保管私钥，按环境/域名通过内核 CDP 注入虚拟认证器；支持可导出私钥的软件库，但无法导出 Apple 密码/iCloud 钥匙串私钥|极佳（零扩展指纹、按站点精细授权隔离）|暂不实施，保留作远期演进|
|**方案三：宿主机物理安全密钥（YubiKey）+ 用户态 CTAP2 桥接**|宿主机物理 Key 经伴生代理转发 APDU 签名；无法复用现有 Bitwarden Passkey，需重新绑定物理 Key|极佳（私钥不出硬件芯片，支持硬件 Attestation）|暂不实施，开发成本高|
|**方案四：手机扫码 Hybrid（caBLEv2）或密码 + TOTP**|Hybrid 依赖桌面与手机之间的 BLE 蓝牙近场验证，OrbStack Linux 容器无蓝牙硬件，大概率不可用；当前版本临时应急只能用密码 + 剪贴板粘贴 TOTP|高|仅作未改造前的临时应急手段|

## 三、方案一目标架构与产品设计（遵循开发铁律：架构至上、拒绝妥协、零兼容性负担）

1. **明确的扩展权限开关与参数语义（彻底根除参数冲突）**
    - 在 Profile 运行配置（`ProfileConfig` / DB / DTO / UI）中引入显式布尔开关 `allow_extensions`（默认 `false`）：
        - **`allow_extensions = false`（默认）**：继续保留 `--disable-extensions`，维持最干净指纹基线与最小权限；前端表单隐藏或禁用下方的扩展配置区。
        - **`allow_extensions = true`（用户勾选“允许扩展”）**：`runner.py` 必须显式接管浏览器启动默认参数，**将 `--disable-extensions` 从启动参数中彻底移除**（不依赖 `cloakbrowser` 硬编码的 `IGNORE_DEFAULT_ARGS`）。
            - **指定扩展模式（选中 1 个或多个扩展）**：向 Chromium 传入 `--load-extension=<dir1>,<dir2>,...` 与 `--disable-extensions-except=<dir1>,<dir2>,...`，精确只放行并加载选定的多个扩展；
            - **自由扩展模式（勾选允许扩展但扩展清单为空）**：既不传 `--disable-extensions` 也不传 `--disable-extensions-except`，允许用户在远端 `chrome://extensions` 自由加载、拖入 `.crx` 或管理扩展（数据持久保存在该 Profile 的 `user_data_dir`）。
2. **受管多扩展资产库与只读容器挂载（废除 UI 手填宿主机盲路径）**
    - 参照本仓 `font_sets`（ADR 029 / ADR 030）与 `MountPlanner` 受管存储契约：
        - **控制面「扩展资产库」**：用户上传扩展包（`.zip` 或 `.crx`），服务端解压并校验 `manifest.json` 合法性，提取扩展 ID、名称、版本与图标元数据，按不可变资产存放到受管存储卷（同步纳入环境备份/恢复点视野）；
        - **多扩展组合选择**：Profile 表单在“允许扩展”勾选后，支持从扩展库**多选、排序/增删多个扩展**（替代当前按逗号 `split(",")` 切分的单行输入框；若需保留高级自定义路径亦必须为结构化列表并受受管根校验）；
        - **只读挂载与运行时隔离**：启动 Browser 容器时，`MountPlanner`（`volume_spec.py`）仅将该 Profile 绑定的那几个扩展目录以 `:ro` 只读挂载进容器（例如 `/run/cbrowser/extensions/<ext_id>`）；未绑定扩展的 Profile 与 Stream 容器完全不可见；扩展运行后的登录态、缓存与本地库均保存在各自 Profile 独立的 `user_data_dir` 内，互不串号。
3. **产品边界与风险提示**
    - 界面明确提示：开启扩展会增加浏览器可探测特征；若在多个隔离身份环境登录同一 Bitwarden 主账号，各环境本地均会留存同步后的密码库缓存，强风控场景建议按业务拆分密码库账号。
    - 涉及代理的 Profile 中，扩展自身访问 Bitwarden 服务端流量走浏览器代理出口策略，不产生直连泄露。

## 四、实施前置验证（Spike 清单）

立项实施前必须在当前固定引擎（Linux arm64 `146.0.7680.177.3`）上实测确认：

1. 去掉 `--disable-extensions` 后，多扩展同时经 `--load-extension` + `--disable-extensions-except` 挂载加载的实际表现（含 `chrome://extensions` 状态与扩展弹窗/后台 Service Worker 活性）；
2. 容器内运行 Bitwarden 官方 Chrome 扩展（纯 JS/WASM）在 `ungoogled-chromium 146` 上登录同步、拦截 `navigator.credentials.create`（`https://webauthn.io`）及 `navigator.credentials.get`（真实账号 Passkey 登录）的完整端到端可行性；
3. 开启扩展对既有防泄露网络策略与指纹一致性门禁的影响。

- 相关条目：`p166`（Profile 高级选项无效/版本错位字段与 `launch_args` 债务清理）
- 测试环境备忘：验证期间在本地实例建有 `0088`（`c9a0f33a-941a-44a6-9c62-5bbc807c275e` / `US-EN-Bitwarden-Test`）。
- 处理：未开
