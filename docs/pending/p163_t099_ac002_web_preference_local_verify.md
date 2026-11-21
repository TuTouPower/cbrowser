---
pid: "p163"
slug: "t099_ac002_web_preference_local_verify"
status: "closed"
resolution: "resolved"
reason: "2026-11-21 本地 Mac 真机补验完成：当前源码下适配网页收到与 Profile 一致的浅/深偏好并采用对应样式、固定白底对照页不受影响、双 Profile 独立偏好均成立，结论回填本条与 d053。"
fix_ref: "s027"
---
# p163 t099 AC-002 本地补验：真实浏览器网页配色偏好与对照页行为

- 来源：t099 遗留（AC-002 为 [deploy]，按用户裁定云端打勾＋处置注记，真实验证延期本地）
- 内容：网页偏好传参（`color_scheme=cfg.color_scheme`）为既有行为、云端未改动，Runner 单测覆盖同一绑定值同时派生原生外壳；但 AC-002 的真实浏览器行为云端不可验。留待本地 Mac 在真实部署上补验：适配网页收到与 Profile 相同的浅/深偏好并采用对应样式、固定白底对照页仍按其样式显示、管理页面主题切换不改变任一远程浏览器配色，用两个可控本地测试页查询偏好并检查渲染、辅以 Viewer 冒烟。
- 处理：闭环（resolved，2026-11-21）。与 p162 同一次真机运行，使用当前 main 源码（`runner.py:712` 的 `color_scheme=cfg.color_scheme` 传参）与固定引擎 `146.0.7680.177.3`，两个可控本地测试页（媒体查询适配页 + 固定白底页）由生产 `BrowserRunner` 打开。
    - 证据：`.scratch/p162_verify_tFCXfj/evidence/runtime_results.json`，8 例全部通过 `verify.py` 像素与 DOM 复核。
    - 实测矩阵：适配页在深色配置下 `matchMedia('(prefers-color-scheme: dark)')` 为真、背景 `rgb(32,33,36)`，浅色配置下为假、背景 `rgb(244,245,246)`；固定白底页在任何配置下背景恒为 `rgb(255,255,255)`；两个 Profile 同时运行时网页偏好各自跟随本 Profile；管理页面主题由前端独立 token 驱动，不参与远程浏览器 `color_scheme` 绑定（t099 前端仅表单说明，无管理主题联动代码）。
    - 未单独执行 Viewer 冒烟：本次以浏览器引擎页面内脚本直接查询媒体偏好，证据强度高于 Viewer 像素间接推断；Viewer 画面链路本身由既有 t019/t061 E2E 覆盖，不因配色偏好重验。
    - 结论：AC-002 真机行为成立。长期结论见 d053 就地修订。
