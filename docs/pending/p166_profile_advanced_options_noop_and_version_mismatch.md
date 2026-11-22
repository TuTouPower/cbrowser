---
pid: "p166"
slug: "profile_advanced_options_noop_and_version_mismatch"
status: "closed"
resolution: "transferred"
reason: "已按 Codex 评估清理决策核实范围并转交 t103"
fix_ref: "t103"
---
# p166 Profile 高级选项无效或版本错位开关与 launch_args 债务清理

- 现象：在新建/编辑环境的「高级」面板（`src/frontend/src/features/profiles/ProfileForm.tsx`）中，多个开关和输入框在当前运行架构与固定内核下实际无效、版本错位或解析损坏：
    1. `拟人化 (humanize)` 与 `拟人化预设 (human_preset)`：前端提示开启后“启动的浏览器会像真人一样操作页面”，但在当前真人 WebRTC 交互与外部 CDP 自动化链路下均不生效；
    2. `自动启动 (auto_launch)`：可配置并持久化，但全仓无任何消费逻辑；
    3. `允许第三方 Cookie (allow_3p_cookies)`、`透明代理 (transparent_proxy)`、`便携 Cookie (portable_cookies)`：会向 `146` 内核注入 SDK 文档标注为 `Chromium 148+` / `151+` 才支持的参数；
    4. `启动参数 (launch_args)`：白名单 22 项中 16 项是 Playwright 默认已传参数，`--lang` 会被覆盖，且前端逗号拆分会破坏 `--accept-lang=en-US,en` 等多值参数。
- 影响：
    1. 产品层面出现多个“安慰剂开关”，误导用户以为已启用拟人化反检、透明代理、便携 Cookie 或自动启动；
    2. `launch_args` 无法满足开启扩展等真实需求，甚至输入白名单唯一支持带逗号的 `--accept-lang=en-US,en` 也会在保存时被切碎报错；
    3. 高级表单信息噪音大，与 `AGENTS.md` 开发铁律“真实彻底、拒绝妥协与半成品”背离。
- 根因（可验证机制与同类位点清单）：
    1. **`humanize` / `human_preset` 架构错位**：
        - `src/backend/cbrowser/runtime_agent/runner.py:709-710` 将 `cfg.humanize` / `cfg.human_preset` 传给 `cloakbrowser.launch_persistent_context_async(...)`；
        - 查 `.venv` 内 `cloakbrowser/human/__init__.py`、`patch.py` 与 `cloakbrowser-0.6.4.dist-info/METADATA:644-909`：`humanize` 并非浏览器内核能力，而是对**启动进程内 Python Playwright `Page`/`Locator`/`Mouse`/`Keyboard` 调用**的客户端 Monkey-Patch，且官方文档第 909 行明确声明通过 CDP 外部连接时不生效；
        - 本系统真人操作经 Selkies WebRTC → X11 XTEST，外部自动化经 `agent_executor` 或外部 Playwright `connect_over_cdp` 直连 Chrome loopback CDP（全仓搜索 `browser_context` 仅在 `runner.py` 初始化默认搜索/查版本及 `probe_collector.py` 探针中调用），因此该配置对核心使用与外部自动化链路均不生效。
    2. **`allow_3p_cookies` / `transparent_proxy` / `portable_cookies` 版本错位**：
        - `runner.py:676-681` 分别注入 `--fingerprint-allow-3p-cookies`、`--fingerprint-transparent-proxy`、`--fingerprint-portable-cookies`；
        - 查 `cloakbrowser-0.6.4.dist-info/METADATA:796-802`：`--fingerprint-allow-3p-cookies` 标明 `Chromium 148+ binary only`，`--fingerprint-transparent-proxy` 与 `--fingerprint-portable-cookies` 标明 `Chromium 151+ binary only`（`docs/pending/p102` 第 125 行亦已记录当前固定 146 不可直接套用高版本 flag）；
        - 当前系统固定 Linux arm64 引擎版本为 `146.0.7680.177.3`（已由 `0088` `chrome://version` 核实），这三个参数在 146 二进制上的真实识别状态未经二进制实测，极可能被静默忽略。
    3. **`auto_launch` 无消费点**：`docs/specs/profile_management.md:32` 已明确记录全仓没有任何后端或前端代码读取该字段执行自动启动。
    4. **`launch_args` 冗余与解析损坏**：
        - `src/backend/cbrowser/launch_args.py:7-41` 允许的 22 个参数中，16 个与 Playwright `chromiumSwitches`（`playwright/driver/package/lib/coreBundle.js`）完全重复（如 `--disable-extensions`、`--disable-background-networking`、`--no-first-run` 等），填与不填一致；
        - `--lang=...` 在 `cloakbrowser.build_args`（`browser.py:1480-1486`）合并用户参数后会被 Profile `locale` 覆盖；
        - `ProfileForm.tsx:864-867` 使用 `event.target.value.split(",")` 拆分参数，会将合法的多值参数 `--accept-lang=en-US,en` 拆成 `["--accept-lang=en-US", "en"]`，触发后端 `InvalidLaunchArgument` 422 拒绝。
    - 已确认同类位点清单：
        - `src/backend/cbrowser/runtime_agent/runner.py:649-717`
        - `src/backend/cbrowser/launch_args.py:7-41`
        - `src/backend/cbrowser/domain/models.py:265-285`、`src/backend/cbrowser/adapters/database/models.py`
        - `src/frontend/src/shared/api/types.ts`、`src/frontend/src/features/profiles/ProfileForm.tsx:204-250, 828-889`
        - `src/frontend/src/i18n.tsx:359-386, 925-952`
    - 建议清理方向（开发铁律：零兼容性负担）：对固定 `146.0.7680.177.3` 二进制实测 3 个高版本 flag；确认无效后连同 `auto_launch`、`humanize`、`human_preset` 从 DB/API/UI 彻底破坏性清除（若未来需要自动化拟人化，归口到 `agent_executor` 客户端执行器侧）；收缩或结构化改造 `launch_args`，将真正有意义的能力产品化为显式开关（如配合 `p165` 的 `allow_extensions` 及按需“静音启动”），消除 `split(",")` 解析 bug。
- 测试缺口：
    - 现有前后端测试（如 `ProfileForm.test.tsx`、`test_launch_args.py`、runner mock 单测）只验证字段能否保存到 DB 以及是否拼进 mock 参数列表，未验证：
        1. 固定 `146.0.7680.177.3` 二进制是否真正识别 `--fingerprint-allow-3p-cookies` / `--fingerprint-transparent-proxy` / `--fingerprint-portable-cookies`；
        2. 外部 CDP 连接场景下 `humanize` 是否真实改变鼠标/键盘行为（当前必然失败）；
        3. 前端 `ProfileForm` 提交带逗号参数值（如 `--accept-lang=en-US,en`）时的序列化与往返测试。
    - 后续改造须补充：146 二进制支持能力验证记录、清理后数据库迁移与 API/UI 契约回归测试，以及多值参数结构化输入测试（若保留 `launch_args`）。
- 线索：基于仓内源码与 `.venv` 内 `cloakbrowser 0.6.4` / `playwright 1.64.1` 静态核对，以及运行环境 `0088`（`c9a0f33a-941a-44a6-9c62-5bbc807c275e`）`chrome://version` 命令行实测；无独立 `.scratch/` 复现脚本。
- 处理：t103；resolution=transferred；reason=已按 Codex 评估清理决策核实范围并转交 t103

## Codex 评估

复核于 2026-11-22，源码基线 `6ccbb18`。在现有 Browser 镜像 `dcb33194200f` 中以临时 Xvfb 和有头持久会话运行 SDK `0.6.4` / Playwright `1.64.1`。容器禁用外网，仅读挂载引擎缓存，测试使用临时 Profile、回环站点和回环代理。通过 `engine_artifacts.py` 验证 Linux arm64 `146.0.7680.177.3` 的 15 个固定文件，`chrome` SHA-256 为 `3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f`。`chrome://version` 只能核对四段 Chromium 版本 `146.0.7680.177`，第五段制品版本由仓内 pin 与摘要确定。仓内另登记 Linux x64 `146.0.7680.177.5`，仅固定压缩包摘要，当前 runner 的解压件完整性校验要求已固定可执行文件摘要。本轮未运行 x64。 [CloakBrowser 146.0.7680.177.3 发布记录](https://github.com/CloakHQ/CloakBrowser/releases/tag/chromium-v146.0.7680.177.3)

### 逐项核对

1. **`humanize` / `human_preset` 的产品行为错位成立。** `runtime_agent/runner.py:702-717` 传入两字段。SDK `browser.py:908-911` 在 Chromium 已启动后才对当前 Python Playwright context 应用 `patch_context_async`，包装 page、locator、mouse、keyboard 等调用。Selkies 输入经 WebRTC 数据通道到 X11 XTEST。`agent_executor/session.py:571-610` 发 CDP `Input.*`，外部客户端经授权隧道到容器回环 CDP，均绕过启动进程的包装。独立 CDP 会话发送两次鼠标移动，开关两态都只收到两个指定坐标。原文的 context 用途清单还漏了默认搜索重试、驱动存活检查和关闭。默认搜索操作走 `goto` / `evaluate` 内 DOM 代码，指纹探针走 `goto` / `evaluate`，两者均无拟人化输入调用。SDK 文档允许外部客户端自行应用包装，启动端设置不会跨客户端传播。 [CloakBrowser 0.6.4 的 humanize 与 CDP 说明](https://github.com/CloakHQ/CloakBrowser/blob/v0.6.4/README.md#framework-integrations)
2. **三个高版本 flag 的版本错位成立，arm64 现已做开关对照。** `runner.py:676-681` 直接拼接。锁定 wheel 的 `METADATA:796-802` 与版本化 README 一致，`allow_3p_cookies` 要求 148+，`transparent_proxy` 和 `portable_cookies` 要求 151+。三个 flag 在开启时都出现在 `chrome://version` 命令行，固定 `chrome` ELF 中均未检出对应 switch 字面量。行为如下。 [CloakBrowser 0.6.4 参数表](https://github.com/CloakHQ/CloakBrowser/blob/v0.6.4/README.md#additional-flags)
    - `allow_3p_cookies`。用 `127.0.0.1` 顶层页嵌入 `localhost` iframe，设置并回读非分区 `SameSite=None; Secure` Cookie。普通 Profile 允许第三方 Cookie 时，flag 开关两态均读到。`profile.cookie_controls_mode=1` 时，两态均读不到，顶层同站对照均读到。现有开关既无法覆盖 Chromium 的阻止设置，也无法用关闭态强制阻止。
    - `transparent_proxy`。分别启停 flag，普通 HTTP 请求都由同一个配置的回环 HTTP 代理收到，均为相同的绝对请求目标。该对照只覆盖普通 HTTP，结合版本文档和二进制结果，足以判定当前产品缺乏受支持的透明代理能力。标准 SDK `proxy=` 与 ADR 038 的 egress 防护有独立实现。
    - `portable_cookies`。开关两态分别在全新 Profile 写同一合成持久 Cookie，SQLite 加密值完全相同且均为 `v10`，`Local State` 均无 `os_crypt.encrypted_key`。复制各自整个 user-data-dir 到新路径，以关态重启仍可读。与 `d044` 的 x64 无 keyring 观察一致。本轮只覆盖同容器复制，跨机器、跨加密后端与真实登出条件未测。
3. **`auto_launch` 无启动消费点成立，误导程度需修正。** 源码引用限于表单和传输、持久化、配置快照与字段分类。「创建并启动」由 `ProfileForm.tsx` 的 `__startAfterCreate` 和 `ProfileCreateDialog.tsx` 的独立启动请求驱动。重启后的协调依赖 `desired_state`。中英文帮助已明确说明保存该值不会自动启动。它仍占用表单位置，且改值会生成运行配置版本并可能显示待应用。
4. **`launch_args` 冗余成立，精确数为 17/22。** 对比 `launch_args.py:7-41` 与 Playwright `chromiumSwitches()`，包括桌面路径实际注入的条件项 `--disable-sync`。SDK `IGNORE_DEFAULT_ARGS` 只排除 `--enable-automation` 和 `--enable-unsafe-swiftshader`，17 项均仍在默认集合。其余五项为 `--lang`、`--accept-lang`、`--mute-audio`、`--disable-translate`、`--disable-blink-features=AutomationControlled`。`--disable-translate` 字面量在固定 ELF 未检出，且 Playwright 已通过 `--disable-features` 禁用 `Translate`。`AutomationControlled` 开关两态实测 `navigator.webdriver=false`，只证实该观测值一致。`--mute-audio` 仅在 Playwright 无头模式默认注入，项目以有头模式运行。固定 146 实测同一 Web Audio 音源在 PulseAudio 监测端从有信号变为全零，属有效功能。 [Playwright 1.64.1 默认开关](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/src/server/chromium/chromiumSwitches.ts) · [Playwright 1.64.1 Chromium 启动实现](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/src/server/chromium/chromium.ts)
5. **语言优先级和表单解析应分别判断。** `build_args` 仅在 SDK 最终拿到 locale 时覆盖 `--lang` 并加 `--fingerprint-locale`。Profile 显式 locale 优先。`locale=None` 且 `geoip=True` 时，`maybe_resolve_geoip` 会先把原始 `--lang` 提升为显式 locale，再填其余 GeoIP 值。`geoip=False` 且 locale 为空时，`--lang` 留在命令行，但单传日语 `--lang` 在本次 Linux 探针中未改变请求头或 `navigator.languages`。同条件单传 `--accept-lang=ja-JP,ja` 则两者都改为日语。显式设置 SDK locale `de-DE` 后，即使 argv 仍含日语 `--accept-lang`，两者均以德语为准。德语用于 SDK 对照，项目 locale 枚举当前只有 `en-US` / `zh-CN`。前端 `ProfileForm.tsx:854-869` 将输入拆成两个元素，复核 `validate_launch_args` 接受完整 `["--accept-lang=en-US,en"]`、拒绝拆分后的 `en`。创建和更新 DTO 把该错误转为 422。经 API 保存的合法条目在编辑界面可展示，改动该输入时才会重新拆分。 [CloakBrowser 0.6.4 参数合并与 GeoIP 源码](https://github.com/CloakHQ/CloakBrowser/blob/v0.6.4/cloakbrowser/browser.py)

### 遗漏位点

- **`extension_paths` 与 p165。** `ProfileForm.tsx:872-889` 同样用逗号拆分。API 接收字符串数组，SDK 又将绝对目录用逗号拼进 `--load-extension` 和 `--disable-extensions-except`。路径内含逗号时边界无法保真。`supervisor/volume_spec.py` 缺少宿主扩展目录映射，任意宿主路径无法直接解析为容器资产。另一个实测修正是固定 146 以当前 SDK 默认参数接收上述两个显式扩展参数时，尽管 argv 仍有 `--disable-extensions`，容器内有效 MV3 目录的内容脚本照常执行。实验中仅从 Playwright 默认值移除 `--disable-extensions`，脚本也照常执行。p165 的空列表观察无法覆盖显式加载路径。关闭态必须同时切断显式加载路径，并验证存量已安装扩展不执行。当前结果仅覆盖合成 MV3 内容脚本，未验证商店安装或 Bitwarden。 [p165](p165_managed_extensions_and_bitwarden_passkey.md) · [CloakBrowser 0.6.4 持久会话说明](https://github.com/CloakHQ/CloakBrowser/blob/v0.6.4/README.md#launch_persistent_context)
- **`restore_session` 文案承诺过强。** `runner.py:682-683` 只在开启时加 `--restore-last-session`。实测存量 Profile 的 Chromium 首选项未要求恢复时，关闭只出现空白页，开启恢复此前两页。若 `Preferences` 已设 `session.restore_on_startup=1`，关闭仍恢复两页。保留该功能，若继续承诺关闭后不恢复，需明确 Profile 设置与原生偏好的优先级并补测。`set_google_default`、`clipboard_sync`、`capture_preview` 均存在独立消费点。
- **清理影响超出原清单。** `api/v1/router.py` 的创建映射、`domain/models.py` 的领域模型和创建／更新／响应 DTO、`adapters/database/repository.py` 的当前行、配置版本、克隆读取、`runtime_agent/runner.py` 的严格快照加载，以及 `fingerprint_verification/probe_collector.py` 的配置摘要都涉及这些字段。运行字段集合由领域模型派生，影响前端差异判断和待应用提示。需重新导出 public/internal OpenAPI、前端生成类型与 `profile_field_classification.ts`，并更新有效 spec、blueprint、旧断言和 fixtures。`profile_config_versions.snapshot` 里的旧 key 也会进入 `ProfileConfig(extra="forbid")`，只删表列会使旧版本启动失败。

### 清理决策

1. **先删除已证实无效的六个 Profile 字段。** 清除 `humanize`、`human_preset`、`auto_launch` 和三个高版本开关的 DB/API/UI、运行参数、探针摘要与翻译。当前固定制品已有充分证据。引擎能力随 pin 变化，等批准新制品并验证真实效果后，再按需引入相应功能。目前保留隐藏字段或动态版本判断只会增加维护面。将来需要拟人化时，由实际发送动作的 `agent_executor` 或外部客户端按调用明确选择。
2. **优先退役通用 `launch_args`，以存量行为盘点为迁移前提。** 对当前行及全部配置快照做只读分类并输出受影响 Profile/版本。确认冗余项后直接归并。若发现有效 `--mute-audio` 使用，将它迁移到显式「静音启动」字段，默认关闭。语言沿用一个权威配置入口，有实际多语言需求时扩展该模型，统一验证原生语言、请求头和 `navigator.languages`。有效 `--accept-lang` 列表、GeoIP 模式下提升为 locale 的 `--lang`、超出当前 locale 枚举的值，以及有行为疑问的 `AutomationControlled`，均需先确定等价映射或由用户裁决再移除。重复语言参数要按 SDK 的实际取值判断，GeoIP 提升取首个匹配项，`build_args` 同 key 合并取末项。若已有 API 工作流确实依赖独立原始参数，备选为小白名单加逐条编辑控件，每条完整传为数组元素，保存、重载和再次编辑都测含逗号值。该方案保留参数优先级和长期验证成本，因此只在确认存在独立需求时采用。
3. **扩展专由 p165 的受管资产与显式权限负责。** 用受管 ID 替换原始 `extension_paths`，默认关闭时既禁用扩展系统也不传显式加载目录，开启时才解析白名单资产并只读挂载。实际验证默认关闭、开启并加载、曾开启后关闭、两个 Profile 互不串用。对 p165 的自由模式，单独验证固定内核的实际安装入口。现有路径若能对应受管资产则明确迁移，无法映射的先列清单，避免升级后无声丢失已加载扩展。
4. **迁移和验收。** 新增前向 Alembic revision，先用可恢复备份演练，原子迁移 `profiles` 和全部版本快照，保留版本号、运行绑定、代理凭证修订号与 Profile 文件。沿用 `0013_profile_identity.py` 的迁移模式，确保 Supervisor 为新实例从迁移后的绑定版本重写 `snapshot.json`，验证在跑环境升级、重启、旧版本引用和克隆。旧 API 字段按严格 DTO 返回 422。用真实引擎断言清理前后应保留的行为、静音输出、语言以及扩展关闭态，单测继续承担参数与契约边界验证。本次现有 `test_launch_args.py` 与 `test_profile_launch_args_api.py` 共通过 23 项，逗号输入的现有表单端到端用例仍缺。
