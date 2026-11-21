---
pid: "p162"
slug: "t099_ac001_native_shell_local_verify"
status: "todo"
---
# p162 t099 AC-001 本地补验：真实有头浏览器原生外壳随 Profile 配色切换

- 来源：t099 遗留（AC-001 为 [deploy]，按用户裁定云端打勾＋处置注记，真实验证延期本地）
- 内容：云端无 Docker/真实引擎，只完成 Runner 启动前向本 Profile 的 Chromium `Preferences` 派生写入（`browser.theme.color_scheme2` 浅 1/深 2、`extensions.theme.system_theme` 固定 0）的实现与单元测试；spike s027 已在固定引擎（CloakBrowser 146.0.7680.177.3 / OrbStack arm64）证明该写入机制本身成立。留待本地 Mac 在真实部署上补验 AC-001 全文：标签栏/地址栏/工具栏/原生菜单随配色呈现、存量 Profile 保存另一配色并以新配置启动后深↔浅双向切换、不同 Profile 同时不同配色，X11 窗口区域与菜单截图取证。
- 处理：未开
