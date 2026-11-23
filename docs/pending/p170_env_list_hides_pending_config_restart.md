---
pid: "p170"
slug: "env_list_hides_pending_config_restart"
status: "closed"
resolution: "transferred"
reason: "已核实根因与范围并转交该 task"
fix_ref: "t106"
---
# p170 环境管理列表不显示配置变更待重启状态

- 来源：用户截图反馈（环境管理页 6 行环境，5 行徽章「运行中」、1 行「启动中」）「我修改配置文件之后，这个环境管理界面还是运行中。我必须要到工作台界面，它才提示我修改了配置，需要重启」。bug-to-pending 分析登记，未在生产代码落修复。
- 现象：
    - 修改配置后停留在「环境管理」页（路由 `/`，`EnvironmentListPage`），行徽章仍按 `runtime.observed_state` 显示「运行中」，不出现任何「配置变更待应用 / 需重启」提示。
    - 进入工作台具体会话页（路由 `/session/:profileId`，`SessionPage`）后，`SessionHeader` / `SessionDetailsPanel` 显示「有待应用配置」横幅及「应用并重启」按钮；进入环境详情非 config 标签页时 `SharedProfileBanners` 显示「运行配置变更待应用」横幅。
    - 用户必须离开环境管理页、进入工作台才感知到配置已变更，环境管理页给出「一切正常运行中」的错误安心信号。
    - 预期：配置版本与运行版本不一致时，环境管理列表同样应显式暴露该环境「配置变更待应用 / 需重启」，而不是只显示运行态徽章。
- 影响：
    - 环境管理列表（`EnvironmentListPage.tsx:53-75, 178-193`，含 `EnvironmentTable` 表格布局与 `EnvironmentCardGrid` 卡片布局）完全不感知配置新鲜度。
    - 工作台默认入口页（`SessionEntryPage.tsx:32-34, 68-80`）同样只按 `observed_state === "running"` 出「运行中」徽章，无待应用提示。
    - 待应用判定逻辑在 3 处复制粘贴且守卫不一致：`SessionHeader.tsx:113-115`、`SessionDetailsPanel.tsx:150-151`、`SharedProfileBanners.tsx:21-26`（后者额外要求 `current_config_version !== undefined`，前两处不检查），任一处改动易漂移。
    - 该信号缺失只影响用户感知与操作时机，不影响后端真实运行状态或配置落盘。
- 根因（可验证机制与分类）：**产品缺陷 / 派生状态未共享 + 展示层漏判**，非环境、非配置、非测试假绿。
    1. 后端配置改动抬升 `Profile.current_config_version`，运行实例保持旧 `runtime.config_version`；前端判定「待应用」的唯一机制是两值不等，没有独立 `needs_restart` / `dirty` 标志位。
    2. 判定表达式 `runtime.config_version !== profile.current_config_version` 只写在工作台/详情 3 个组件内（见上）。`EnvironmentListPage` 只调用 `useProfilesCollectionQuery`，`projectionToRuntime` 把 `projection.config_version` 写入 runtime，但**从不与 `item.current_config_version` 比较**，也不渲染 pending Banner。`ProfileCollectionItem` 本身同时携带两个版本字段，故**数据齐备、缺的是判定与渲染**，不是接口缺字段，也不是取数/刷新时序问题。
    3. 列表行徽章来自 `shared/presentation.ts:20-31` 的 `environmentStatusDescriptor(observed_state)`，只表达运行态，不表达配置新鲜度，因此版本不等时仍显示「运行中」。`SessionEntryPage.tsx:77` 固定 `tone="running"`，同理。
    4. 已确认同类位点（同一机制，合并进同一修复范围）：`EnvironmentListPage.tsx`（表格 + 卡片两种布局共用 `visibleRows`）、`SessionEntryPage.tsx`、以及上述 3 处重复判定应统一到单一派生状态/共享组件。
    5. 未确认残余（单列，不计入已确认范围，需产品裁决）：配置编辑页 `ConfigTab` 当前刻意不渲染 `SharedProfileBanners`（`ProfileDetailPage.tsx:191-204`），编辑期间是否提示待应用；以及列表是仅加徽章提示还是同时提供行内「应用并重启」动作（现有动作为 `useApplyDisplaySettingsMutation` = stop + setDesiredState running，`useProfilesQuery.ts:632-719`）。
- 测试缺口：
    1. `EnvironmentListPage.test.tsx` 的 5 种状态徽章用例（`:653-690`）与全部 fixture 把 `current_config_version` 与 `config_version` 都钉为 `1`（`:92, :111, :133`），没有任何版本不等场景，因此列表漏判全绿。
    2. `SessionEntryPage.test.tsx` 同样把两版本都钉为 `1`（`:83, :102, :121`），无待应用断言。
    3. 对照：`SessionHeader.test.tsx:356-373, 434, 467, 481` 明确覆盖版本相等不显示、版本不等显示横幅并触发重启，证明工作台路径被测、列表路径未测。
    4. 修复后须补：在 `EnvironmentListPage.test.tsx` 以 `current_config_version=2 / runtime.config_version=1` 断言表格行与卡片行各自出现待应用信号（不刷新页面），并断言 SSE/版本抬升后由「运行中」平滑转为待应用；在 `SessionEntryPage.test.tsx` 补同类断言；统一三处判定后保持/迁移 `SessionHeader` 既有断言。
- 线索：
    - 最小复现：`.scratch/repro_env_list_config_pending/repro.test.tsx`（构造 `current_config_version=2`、`runtime.config_version=1`、observed=running 的 collection 行渲染 `EnvironmentListPage`）。
    - 对照测试同文件第二个用例：同一错配数据渲染 `SharedProfileBanners`，`profile-apply-pending` 横幅正常出现。
    - 运行：`cd src/frontend && npx vitest run --config ../../.scratch/repro_env_list_config_pending/vitest.config.mjs`。
    - 实测：列表用例 `ROW TEXT: Alpha-DirectWindowsRunningOpen`、徽章 `Running`，待应用断言 `expected false to be true`；对照用例通过。证明同一数据下工作台能提示、环境管理页不能。
- 处理：t106；resolution=transferred；reason=已核实根因与范围并转交该 task
