---
tid: "t099"
slug: "profile_browser_color_scheme"
title: "环境配色统一驱动浏览器外壳与网页偏好"
status: "done"
branch: "t099_profile_browser_color_scheme"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "4e007a694f1b5d3ada39ee29caa687df8198727f"
spec_source_sha: "4e007a694f1b5d3ada39ee29caa687df8198727f"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 契约处置（2026-11-21 云端执行）：spike s027 已在 Mac 本地完成并记录于 docs/spikes/s027_profile_native_color_scheme（固定引擎 CloakBrowser 146.0.7680.177.3 / OrbStack arm64 实测：启动前向本 Profile 的 Chromium `Preferences` 写入 `browser.theme.color_scheme2` 浅 1 / 深 2 与 `extensions.theme.system_theme` 0，存量 Profile 浅→深→浅、双 Profile 独立配色、固定白底对照页不变均成立），云端不重做。AC-001/AC-002 为 [deploy]，按用户裁定在 task.md 契约区写处置注记后打勾，真实验证分别登记 p162/p163 留待本地；AC-003 由自动测试验证后打勾。
- 后端落点：runtime_agent/runner.py 的 BrowserRunner.start() 在 seed_widevine_hint 后、launch_persistent_context_async 前调用新增 `_apply_native_color_scheme(cfg.color_scheme)`：读本 Profile `Default/Preferences`（缺失/损坏/非 dict 按空文档起步，与 Chromium 自身恢复一致），setdefault 式合并两键（非 dict 中间层替换为 dict），其余内容保留，经既有 atomic_write_json 原子写回。写入失败按失败封闭处置：异常直接传播使启动失败，不静默以错配外壳启动（与字体集不可用同级）。网页偏好沿用既有 `color_scheme=cfg.color_scheme` 传参未改。
- 前端落点（AC-003）：ProfileForm 配色 Row 增加 FieldHelp 说明（与其它字段同款），i18n 新增 formColorSchemeHelp 中英文：外壳（标签栏/地址栏/工具栏）随配色切换、支持适配的网站跟随偏好（自定样式者不受影响）、配置随下一次浏览器启动生效。ProfileForm.test 新增双语说明断言（英文经渲染 tooltip、中文经字典）与深色回显用例；选项保存/回显沿用既有路径未改。
- 文档闭环：specs profile_management / ui_design_system / fingerprint_platform 更新口径并登记 t099；blueprint browser_runtime / domain / testing 同步。
- 定向验证：后端新用例 test_t099_native_color_scheme 4 例 + test_runtime_agent / test_runtime_agent_faults 共 44 例全过；前端 ProfileForm.test 18 例全过（16 既有 + 2 新增）。
- 门禁（证据 gate-t099-final1）：protocol_drift_check / requirements_check / design_lint / design_check / contract / frontend_build 全部 exit 0。unit 2430 passed，5 failed + 10 errors 与云端基线集逐条一致（t063×2、t068×2、t095×1 failed 与 t063/t068 的 10 errors；2430 较 t098 基线 +4 为本 task 新增用例）。integration 220 passed、11 errors（test_normal_exit_replay / test_supervisor_rpc / test_supervisor_manual_retry / test_supervisor_status_truth，均为隔离 API 子进程就绪 setup 错误），四文件单跑 11/11 通过，定性负载 flake。frontend_test 739 passed、3 failed 全为 5000ms 超时（ConfigTab 保存回显、ProfileForm 时区对齐、SettingsPage i18n 切换，后两者为既有 flake 用例），三文件单跑 24/24 通过，定性负载 flake。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-21T14:37:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t099_gen_f001|minor|已修|后端单测原只直调私有方法，start() 调用点与启动前顺序无自动看护；已新增 start 级用例（启动接缝打桩、fake launch 在启动时刻读 Preferences 断言原生值已写入且与网页偏好同源同值）|tests/unit/test_t099_native_color_scheme.py|
|t099_gen_f002|minor|已修|中文说明原仅断言 i18n 字典；已新增 zh locale 渲染用例（localStorage 置 zh 后渲染表单、聚焦帮助按钮断言 tooltip 为中文说明全文）|src/frontend/src/features/profiles/ProfileForm.test.tsx|

处置后定向复跑：后端 test_t099_native_color_scheme 5/5、前端 ProfileForm.test 19/19 全过（新增用例均在门禁之后补入，门禁证据 gate-t099-final1 覆盖其余交付面）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001/AC-002 按用户裁定打勾，真实验证延期本地 p162/p163；AC-003 自动测试验证）
- 测试：门禁 gate-t099-final1——protocol/requirements/design×2/contract/frontend_build exit 0；unit 2430 passed、5 failed + 10 errors 与云端基线集逐条一致；integration 220 passed、11 errors 为子进程就绪 flake（单跑 11/11 过）；frontend_test 739 passed、3 超时 flake（单跑 24/24 过）。审阅轮 1 后补入的两条看护用例定向复跑全过（后端 5/5、前端 19/19）
- 黑盒：云端无 Docker/真实引擎，真机黑盒验证延期本地（p162/p163）；写入机制已由 spike s027 在固定引擎实测成立
- review：single 两轮，轮 2 PASS、零未处置 finding（轮 1 两条 minor 全部已修并经轮 2 复核消除，含基线可红实证）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Runner 启动前把绑定配色派生写入本 Profile 的 Chromium Preferences（原生外壳主题 + 系统主题固定 Chromium 自带），与网页偏好同源同值、写入失败封闭；表单配色字段新增中英文说明。遗留：p162（AC-001 本地补验）、p163（AC-002 本地补验）。

### 长期文档闭环

- specs profile_management / ui_design_system / fingerprint_platform 已更新口径并在 front matter 登记 t099；blueprint browser_runtime / domain / testing 同步。spike s027 已有 report 与采纳结论（机制成立、按其形状落地），本 task 即其后续。
