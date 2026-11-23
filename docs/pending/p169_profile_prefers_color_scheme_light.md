---
pid: "p169"
slug: "profile_prefers_color_scheme_light"
status: "closed"
resolution: "duplicate"
reason: "用户要求关闭；本条为深色配置配色同源领域的未确证再观察（疑运行时重建时序，非新确证缺陷），已被 p157/t099 覆盖范围包含；未授权重启验证前不作为独立缺陷跟踪"
fix_ref: "p157"
---
# p169 深色 Profile 重建后网页 prefers-color-scheme 仍为 light 导致深浅闪烁

- 现象：用户报告 japan cn 环境（profile `9ed642ad-0fea-43af-be8b-f8ebf9667982` / 0086，容器 `cbrowser-0086-browser`）操控时界面闪来闪去，已设置深色模式却「有时闪成白的」。截图为 X.com 生日选择页（外壳深色、年份原生下拉呈浅色）。
- 影响：深色 Profile 的网页内容区与原生外壳配色不一致，加载/导航/操控瞬间出现深浅闪烁。与 p157（已转 t099，原生外壳未变黑）同源领域；p157/t099 已在 2026-11-21 真机补验通过（p162/p163），本条是验收后新观察到的残留状态。
- 根因：未确证，不硬写。已验证事实：
    1. DB `profiles.color_scheme` 为 `dark`（`docker exec cbrowser-api` 查 `/data/db/cbrowser.db`）。
    2. 容器内 `Default/Preferences`：`browser.theme.color_scheme2=2`（dark）、`extensions.theme.system_theme=0` → 原生外壳主题已正确深色。
    3. 但当前网页 `matchMedia('(prefers-color-scheme: dark)').matches=false`、`light=true` → 网页偏好仍是浅色。即「外壳深色、网页浅色」不一致，可解释深浅闪烁。
    4. 代码传递链完整：`runner.py:752 color_scheme=cfg.color_scheme` → `stealth_launch.py:160-161 context_kwargs["color_scheme"]` → cloakbrowser 0.6.4 `launch_persistent_context_async` 透传 Playwright context。
    5. 对照 p124 隔离引擎实测：`dark` 配置下网页 `prefers-color-scheme` 应为 dark，本实例实测为 light，疑为运行时重建/重启时序导致 context 仿真未应用（环境/时序）而非配置传递缺陷。
    6. 该 profile 刚经历重建：CDP 端口 40181→36741、runtime_instance_id 变化、容器集合新增 0089。
        分类待定：(a) 重建/重启时序导致 Playwright `color_scheme` 仿真未应用（环境/时序）；(b) 引擎在 persistent context 重建路径丢失仿真（产品缺陷）。需授权在维护窗口重启 0086 或用测试 profile 复现启动瞬间才能区分。
- 测试缺口：无可自动断言「dark profile 启动后网页 `matchMedia('(prefers-color-scheme: dark)')===true`」的端到端门禁；p162/p163 真机补验只覆盖启动当下，未覆盖 profile 重建/重启后的持续状态。建议在运行就绪门禁加入网页偏好断言并覆盖重建路径。
- 线索：`.scratch/bug_dark_mode_flash.md`（完整复现记录、证据矩阵、CDP 读值、Preferences 值、同类位点为 runner.py:672 外壳路径与 :752 网页路径）。
- 处理：p157；resolution=duplicate；reason=用户要求关闭；本条为深色配置配色同源领域的未确证再观察（疑运行时重建时序，非新确证缺陷），已被 p157/t099 覆盖范围包含；未授权重启验证前不作为独立缺陷跟踪
