---
pid: "p162"
slug: "t099_ac001_native_shell_local_verify"
status: "closed"
resolution: "resolved"
reason: "2026-11-21 本地 Mac 真机补验完成：当前源码 BrowserRunner.start() 在固定引擎真实 X11 部署上随 Profile 配色切换原生外壳，双向切换、双 Profile 独立、菜单绘制、白底对照均成立，结论回填本条与 d053。"
fix_ref: "s027"
---
# p162 t099 AC-001 本地补验：真实有头浏览器原生外壳随 Profile 配色切换

- 来源：t099 遗留（AC-001 为 [deploy]，按用户裁定云端打勾＋处置注记，真实验证延期本地）
- 内容：云端无 Docker/真实引擎，只完成 Runner 启动前向本 Profile 的 Chromium `Preferences` 派生写入（`browser.theme.color_scheme2` 浅 1/深 2、`extensions.theme.system_theme` 固定 0）的实现与单元测试；spike s027 已在固定引擎（CloakBrowser 146.0.7680.177.3 / OrbStack arm64）证明该写入机制本身成立。留待本地 Mac 在真实部署上补验 AC-001 全文：标签栏/地址栏/工具栏/原生菜单随配色呈现、存量 Profile 保存另一配色并以新配置启动后深↔浅双向切换、不同 Profile 同时不同配色，X11 窗口区域与菜单截图取证。
- 处理：闭环（resolved，2026-11-21）。真机验证在目标 Mac M1 Max / OrbStack arm64 上执行：以固定引擎 `146.0.7680.177.3`、真实 `BrowserRunner`、真实 Xvfb/Openbox 与真实 X11 绘制，挂载**当前 main 源码**（`src/backend`）覆盖镜像内旧代码，并把 spike s027 的手工 Preferences 写入置空——确保生效路径是生产 `runner.py:622` 的 `_apply_native_color_scheme`。
    - 证据：`.scratch/p162_verify_tFCXfj/evidence/`（`runtime_results.json` + 8 组窗口/菜单 PNG），由 s027 的 `verify.py` 按像素区域独立复核 8/8 通过。
    - 实测矩阵：同一 Profile 深→浅→深→浅双向切换，标签栏 `(31,32,32)↔(211,227,253)`、地址栏 `(40,40,40)↔(237,242,250)`、工具栏 `(60,60,60)↔(255,255,255)`、菜单随动且菜单实际绘制；两个 Profile 同时运行一个深色一个浅色；固定白底对照页主体恒为 `(255,255,255)`。Preferences 回读 `native=2/1`、`system=0`，与 t099 生产实现一致。
    - 结论：AC-001 真机行为成立。写入机制见 d053，本次为当前源码生产路径的本地补验；管理页面主题切换不改变远程浏览器配色属 AC-002（见 p163）。原始证据在 `.scratch/`（临时目录，不入库）；长期结论见 d053 就地修订。
