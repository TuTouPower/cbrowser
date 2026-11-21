# Task review t099（reviewer_focus: 通用）

- task：`t099_profile_browser_color_scheme`
- spec：`docs/tasks/t099_profile_browser_color_scheme/task.md`
- diff_anchor：`4e007a694f1b5d3ada39ee29caa687df8198727f`
- target：`git diff 4e007a694f1b5d3ada39ee29caa687df8198727f`
- round：1
- reviewed_at：2026-11-21T14:36:47+08:00

reviewed_scope: 0d4525410138d244

## Findings

### t099_gen_f001 - 后端单测直调私有方法，start() 调用点与启动前顺序无自动测试看护

- 严重度：minor
- 锚点：行为缺陷（测试看护缺口）+ 若日后 `start()` 内的调用被删除或移到启动之后，现有单测仍全绿，原生外壳会静默与绑定配色错配而无人察觉
- 位置：`tests/unit/test_t099_native_color_scheme.py:49`（四例均直调 `runner._apply_native_color_scheme(...)`）；生产唯一调用点 `src/backend/cbrowser/runtime_agent/runner.py:622`，网页偏好传参在 `src/backend/cbrowser/runtime_agent/runner.py:712`
- 问题：四例单测真实断言了 Preferences 落盘内容（浅 1 / 深 2、`system_theme` 0、既有内容保留、损坏文件重建），reviewer 定向复跑 4/4 通过；但没有任何自动测试经过 `start()` 验证「启动前以 `cfg.color_scheme` 调用该方法」。本轮以代码审读复核调用点存在且位于 `launch_persistent_context_async` 之前、与网页偏好同源同值，当前实现无缺陷；缺口仅在回归看护强度。
- 建议：在既有 runner 启动接缝测试（如字体门禁的 fake launch 模式）中补一例断言启动后 Preferences 已写入绑定配色，或至少断言 fake launch 被调用时 Preferences 已落盘。

### t099_gen_f002 - 中文说明只断言字典字符串，未经表单以中文 locale 渲染

- 严重度：minor
- 锚点：AC-003 测试强度 + 中文 tooltip 若因 locale 接线问题不显示，现有测试无法发现
- 位置：`src/frontend/src/features/profiles/ProfileForm.test.tsx:843`
- 问题：该用例以英文渲染表单并断言 tooltip 文本等于 `en.formColorSchemeHelp`，中文仅对 `zh.formColorSchemeHelp` 字典字符串做子串断言（外壳 / 跟随 / 下一次浏览器启动生效），未以中文 locale 渲染表单验证 tooltip 实际呈现。实现本身无缺陷：配色 Row 的 FieldHelp 在新建/编辑共用的同一 JSX 上无条件渲染（`src/frontend/src/features/profiles/ProfileForm.tsx:764`），双语条目均存在（`src/frontend/src/i18n.tsx:391`、`src/frontend/src/i18n.tsx:957`），reviewer 定向复跑 ProfileForm 全套 18/18 通过（含深色回显用例）。
- 建议：补一例以中文 locale 渲染表单、聚焦配色帮助按钮并断言 tooltip 呈现中文说明，或将既有用例参数化到双语各跑一次。

## 结论

- 本轮新发现：2 条，均为 minor，无 critical / important
- 未进表的提示：无
- 总体判断：实现与契约一致——Runner 在启动前把绑定配色派生写入本 Profile 的 Preferences（浅 1 / 深 2、`extensions.theme.system_theme` 固定 0、既有内容保留、损坏按空文档重建、写入失败经顶层 CLI 处理以退出码 1 封闭），与 spike s027 在固定引擎实测的合并语义（`docs/spikes/s027_profile_native_color_scheme/code/probe.py` 的 `apply_native_mode`）一致；网页偏好仍由同一 `cfg.color_scheme` 传参；前端双语说明覆盖外壳随配色切换、适配网站跟随偏好、固定样式不受影响、下一次启动生效三点，选项保存/回显路径未改。契约区 drift 仅为打勾与用户裁定处置注记的新增，AC 正文未变；未知契约清单已由 s027 实测结论收敛，无残留 UNVERIFIED 标记；范围外改动未见（存储格式、支持枚举、管理界面主题均未动）。门禁证据与 progress.md 记录一致（protocol/requirements/design/contract/frontend_build 全过；unit/integration/frontend 的失败与超时为既有基线与负载 flake，归因未逐条复跑全量门禁，按任务约束以定向复跑代替：后端新单测 4/4、前端 ProfileForm 18/18 当场复跑通过）。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。打勾与契约区处置注记一致，真实验证已登记 p162 留待本地；云端可做部分（启动前派生写入、同源同值、单测覆盖）经代码审读与单测复跑核实，写入机制由 spike s027 固定引擎实测成立。
- AC-002：TICK-VALID，trust_prior。打勾与契约区处置注记一致，真实验证已登记 p163 留待本地；网页偏好沿用同一绑定值传参未改（runner.py:712），与原生派生同源由单测与代码审读核实。
- AC-003：TICK-VALID，re_verified。定向复跑 ProfileForm.test.tsx 18/18 通过，含双语说明断言与深色回显用例；i18n 双语条目与三点契约内容逐项核对一致。

coverage = 1 / 3

建议合并前人工抽查 trust_prior 项

verdict: PASS

## Round 2 (2026-11-21T14:42:40+08:00)

- task：`t099_profile_browser_color_scheme`
- diff_anchor：`4e007a694f1b5d3ada39ee29caa687df8198727f`
- target：`git diff 4e007a694f1b5d3ada39ee29caa687df8198727f`
- round：2

reviewed_scope: 5feee318d150cb78

## Findings

本轮零新发现（clean）。

## 结论

- 前轮 finding 复核：
    - t099_gen_f001（minor，已消除）：diff 核实新增 start 级用例 `tests/unit/test_t099_native_color_scheme.py:110` 的 `test_start_writes_native_scheme_before_launch`——经真实 `BrowserRunner.start()` 路径运行，仅在启动接缝打桩（引擎二进制、字体校验、CDP guard 等），被测的 `_apply_native_color_scheme` 调用与顺序未被 mock；fake launch 在被调用时刻读取 `Default/Preferences` 并存入 `captured["preferences_at_launch"]`（同文件:206），随后断言启动时刻原生值已落盘（`color_scheme2 == 2`、`system_theme == 0`，同文件:221-223）且传给 launch 的网页偏好同源同值（`captured["color_scheme"] == "dark"`，同文件:225；生产传参点 `src/backend/cbrowser/runtime_agent/runner.py:712`、写入调用点同文件:622 在 launch 之前，未变）。非假绿实证：reviewer 将该用例原样放到基线代码（`git archive` 锚点导出至临时目录，基线 runner 无 `_apply_native_color_scheme`）单跑，结果红——fake launch 读 Preferences 时 `FileNotFoundError`（启动时文件不存在），1 failed；当前代码定向复跑该文件 5/5 通过。
    - t099_gen_f002（minor，已消除）：diff 核实新增 zh locale 渲染用例 `src/frontend/src/features/profiles/ProfileForm.test.tsx:866` 的 `color scheme help renders in Chinese under the zh locale`——渲染前 `localStorage.setItem("cbrowser.locale", "zh")`（该键为 `I18nProvider` 的真实 locale 存储键，`src/frontend/src/i18n.tsx:1167` 的 `STORAGE_KEY`，初始 locale 由其检出），以中文无障碍名定位帮助按钮、聚焦后断言 tooltip 文本等于 `zh.formColorSchemeHelp` 全文，并在 `finally` 中清除该键防污染；不是字典直断。reviewer 定向复跑 ProfileForm.test.tsx 19/19 通过，含该用例与英文 tooltip 用例（同文件:843）。
- 本轮新发现：0 条
- 未进表的提示：轮 1 后增量经 diff 核实仅为上述两条测试（后端测试文件新增 start 级用例、前端测试新增 zh 渲染用例及 `zh` 导入）与 progress.md 处置记录；生产代码 diff 与轮 1 一致（`runner.py` +50、`ProfileForm.tsx` +10、`i18n.tsx` +4，无新增生产变更），文件集与轮 1 相同，无范围外改动。修复过程未引入新问题：新用例的打桩仅限启动接缝，未 mock 被测逻辑；zh 用例的 localStorage 写入有 `finally` 清理。
- 总体判断：轮 1 两条 minor 均已真修且新用例经基线红验证与定向复跑证明非假绿，无未解决 critical / important，本轮 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。打勾与契约区处置注记一致，真实验证已登记 p162 留待本地；云端可做部分本轮经定向复跑后端 5/5（新增 start 级用例断言启动前写入与同源同值）及基线红验证独立核实，写入机制由 spike s027 固定引擎实测成立。
- AC-002：TICK-VALID，trust_prior。打勾与契约区处置注记一致，真实验证已登记 p163 留待本地；网页偏好传参未变（`src/backend/cbrowser/runtime_agent/runner.py:712`），与原生派生同源同值由新 start 级用例在 launch 时刻同时断言两路值核实。
- AC-003：TICK-VALID，re_verified。定向复跑 ProfileForm.test.tsx 19/19 通过，新增 zh locale 渲染用例以中文 locale 真实渲染表单并断言 tooltip 为中文说明全文，英文 tooltip、深色回显用例同套通过。

coverage = 1 / 3

建议合并前人工抽查 trust_prior 项

verdict: PASS
