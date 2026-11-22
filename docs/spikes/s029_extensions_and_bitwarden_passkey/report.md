---
slug: "extensions_and_bitwarden_passkey"
status: "completed"
sid: "s029"
---

# Spike report: 固定 146 引擎受控多扩展、ID 连续性与 Bitwarden Passkey

## 问题

1. 自由模式（去掉 `--disable-extensions` 且不传 `--load-extension` / `--disable-extensions-except`）下，固定 `146.0.7680.177.3`（`ungoogled-chromium`）的实际可用扩展安装入口是哪些（Chrome Web Store 在线安装 / `.crx` 拖放或打开 / 开发者模式加载解压目录）？安装后在同 Profile 重启时能否持久保持，并在切回关闭态或受管模式时正确失效或被拒绝？
2. 去掉 `--disable-extensions` 后加载多扩展时，含/不含 `manifest.json["key"]` 的解压扩展在挂载路径变更前后的 `chrome.runtime.id` 与 `chrome.storage.local` 连续性如何？官方 Bitwarden 扩展在固定 `146` 内核和严格代理拓扑下能否完成登录同步与真实 WebAuthn `navigator.credentials.create/get` Passkey 闭环？

## 成功判据

- 隔离有头容器内逐项实测自由模式 3 个候选入口并形成明确结论，完成持久化、切回关闭态停用与切入受管模式拒绝未授权扩展实证。
- 对比同一持久化 Profile 下带 `key` 与不带 `key` 扩展在路径切换前后的 `chrome.runtime.id` 与 `chrome.storage.local` 读取结果。
- 真实加载官方 Bitwarden 扩展（`2026.11.0`）并通过仅代理可达的 Vaultwarden 后端登录同步后，在 HTTPS 网页真实完成 Passkey 注册（`create`）与认证（`get`）。

## 尝试

- `docs/spikes/s029_extensions_and_bitwarden_passkey/code/probe.py`：使用真实 `cbrowser-browser:2d93270-IDrqH2` 镜像（linux/arm64、Xvfb、Openbox、PulseAudio、真实 Windows 字体集与 `/data/engine-cache/chromium-146.0.7680.177.3/chrome`），验证默认关闭态、`--disable-extensions` 移除后的自由模式 3 个候选入口、`user_data_dir` 持久化、切回关闭态、切入受管双扩展拒载，以及带 `key` 与无 `key` 扩展跨挂载路径（`v1` -> `v2`）ID/存储实验。
- `docs/spikes/s029_extensions_and_bitwarden_passkey/code/probe_bitwarden_passkey.py`：在隔离 Docker 网络 `s029-vw-net` 启动 `ghcr.io/dani-garcia/vaultwarden:alpine`（仅通过容器内局部 HTTP CONNECT 代理向浏览器暴露 `https://vault.s029.local:8443` 与 WebAuthn 测试页 `https://rp.s029.local:8443/webauthn`，无宿主直连 DNS），并发加载官方 `bitwarden.crx`（提取 CRX3 `SignedHeaderData.crx_id` 对应 RSA 公钥并注入 `manifest.json["key"]`）与合成扩展，实测登录、Vault 同步、Passkey 保存与 Passkey 登录。

## 证据

|试验场景|实测结果|核心观察与关键指标|
|---|---|---|
|默认关闭态（`1a_off`）|已禁扩展|`--disable-extensions` 在 argv 中；`chrome://extensions` 项数 0；Service Worker 0|
|自由模式候选 1：CWS（`1b_free.candidate1_cws`）|不可用|顶部显示 `Switch to Chrome to install extensions and themes`；`Add to Chrome` 按钮 `disabled: true`|
|自由模式候选 2：`.crx` 打开与拖放（`1b_free.candidate2_crx`）|不可用|开发者模式关/开下 `file://.../tiny_test.crx` 仅触发下载，JS `DragEvent` 拖放无扩展条目新增|
|自由模式候选 3：开发者模式 `Load unpacked`（`1b_free.candidate3_load_unpacked`）|可用且持久|点击 `Load unpacked` 触发 GTK3 选择目录 `/tmp/.../ext_free`，内容脚本注入 `kdccmddloggmobllclogjlbjinbkkdnp`，Service Worker 激活；无参重启自由模式仍保持生效|
|自由态切回关闭态（`1d_cut_back_off`）|完全停用|恢复 `--disable-extensions` 且不传加载参数后，既有自由模式扩展条目 0、`content_script_attr: null`、Service Worker 0|
|自由态切入受管模式（`1e_managed_refuses_free`）|精确拒绝|传入 `--load-extension` + `--disable-extensions-except` 仅 2 个受管扩展后，两受管扩展执行而既有自由扩展 `free: null` 未运行|
|ID 连续性：带 `key` 移动路径（`v1` -> `v2`）|保持不变|`knbohljdmgknocmlihddnkkmcigcnnab` 不变，重启后 `chrome.storage.local` 原封读回 `probeToken: "secret-keyed"`|
|ID 连续性：无 `key` 移动路径（`v1` -> `v2`）|发生漂移|`ooeeofcnhjbcbnoilllhmjfoaooiomae` -> `gckbbgbcjebjkhckmndolcegjdimcafe`；原 `probeToken` 丢失|
|官方 Bitwarden + Vaultwarden + Proxy + Passkey|全链路通过|并发 2 扩展 SW 正常；Vault 登录同步经代理 `CONNECT vault.s029.local:8443`；`create` 弹出「Save passkey as new login」并写 cipher，返回 `id=N3zWIDhLQtam8aOKTh1NRg`（`attestationLen=178`）；`get` 点击 `s029@example.com` 凭据签名返回同 ID、`authDataLen=37`、`sigLen=72`、`userHandle=AQIDBAUGBwg`|

## 结论

1. 自由模式在 `ungoogled-chromium 146.0.7680.177.3` 上仅\*\*「开启开发者模式 -> Load unpacked（加载已解压的扩展程序，通过 GTK3 目录选择器读取容器内文件/目录）」\*\*为可用且重启持久化的安装入口；CWS 在线一键安装与本地 `.crx` 直接打开/拖放在当前固定 `ungoogled-chromium` 上均不可用。
2. 受管扩展必须在受管目录解包并核验 `manifest.json["key"]`（CRX3 按 `SignedHeaderData.crx_id` 选择匹配 RSA 公钥回写 `manifest.json["key"]`），确保任意挂载路径与旧 `extension_paths` 迁移前后 `chrome.runtime.id` 与本地扩展存储严格连续；无 `key` 且目录变更会导致 Chromium 重算路径哈希 ID 并丢弃原有存储。
3. 显式接管 Playwright `ignore_default_args` 移除 `--disable-extensions` 后，官方 Bitwarden MV3 扩展与多扩展并发、代理严格转发、Vaultwarden 同步及 WebAuthn `navigator.credentials.create/get` Passkey 端到端链路完全可行，无代理绕过。

## 是否采纳

- 决定：是。
- 理由：三个核心未知技术问题均获真实容器与 `146.0.7680.177.3` 内核实测确认，可冻结 `t104` 实施契约。
- 后续 task：t104。
- 无需后续理由：不适用。

## 关联 findings

- [d055 固定 146 引擎自由模式可用开发者模式加载解压目录，CRX3 需提取公钥保持 ID，Bitwarden Passkey 代理链路可行](../../findings/d055_extensions_and_bitwarden_passkey.md)
