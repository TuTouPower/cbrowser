# Task spec

## 背景

用户 2026-11-23 反馈：修改配置后停留在「环境管理」页（`EnvironmentListPage`，路由 `/`），行徽章仍是「运行中」，必须进入工作台具体会话页（`SessionPage`，路由 `/session/:profileId`）才看到「有待应用配置 / 应用并重启」提示。核实结论：判定「配置变更待应用」的唯一机制是 `runtime.config_version !== profile.current_config_version`，该表达式只写在工作台/详情 3 个组件内；`EnvironmentListPage` 的 collection 行已同时携带两个版本字段，但 `projectionToRuntime` / `visibleRows` 从不比较，徽章只取 `observed_state`；工作台入口页 `SessionEntryPage` 同样漏判。属产品缺陷（派生状态未共享、展示层漏判），非取数/刷新时序、非接口缺字段。用户裁决：统一判定，环境管理列表在暴露待应用状态的同时提供行内「应用并重启」，避免来回跳转。

## 契约区

### 范围

- 把「配置变更待应用」判定从 `SessionHeader` / `SessionDetailsPanel` / `SharedProfileBanners` 三处复制表达式提升为单一共享派生状态或判定函数，统一守卫口径（无 runtime 投影、无 `current_config_version` 时不误报）。
- 环境管理列表表格（`EnvironmentTable`）与卡片（`EnvironmentCardGrid` / `EnvironmentCard`）每行一致暴露待应用状态，并提供行内「应用并重启」入口，复用现有 `useApplyDisplaySettingsMutation`（stop + setDesiredState running），pending/error 按目标 Profile 隔离，迟到响应不污染已切换的行。
- 工作台入口页 `SessionEntryPage` 的运行中环境列表一致暴露待应用状态，并提供不与 `<Link>` 嵌套冲突的行内应用入口。
- 停留在环境管理页不刷新、不导航时，后端抬升配置版本后由 SSE / 查询更新把目标行从普通运行态转为待应用态。
- 测试补齐：列表表格/卡片、工作台入口、三处既有工作台判定的统一回归。

### 非范围

- 不改后端 `config_version` 抬升/快照语义、SSE 事件协议、OpenAPI 契约、DB schema 与迁移。
- 不改元数据 / `capture_preview` / 同值提交不生成版本的版本三分规则。
- 不改 `ConfigTab` 编辑期是否显示待应用横幅的现有行为。
- 不新增 apply 后端接口；不引入新的「应用并重启」网络动作语义。
- 不做大规模文案重设计，复用既有 apply pending 文案键。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：停留在环境管理页，某行 `current_config_version` 与 `runtime.config_version` 不等且该环境仍在运行时，表格布局该行显示待应用提示；两版本相等或该行无 runtime 投影时不显示。
- [ ] AC-002：切换到卡片布局，同一行按与表格完全一致的口径显示或不显示待应用提示，不出现一种布局显示、另一种不显示的漂移。
- [ ] AC-003：表格与卡片布局的待应用行提供行内「应用并重启」入口；点击后仅目标环境经历停止并以新版本重新运行，应用完成后该行待应用提示消失，其它行不受影响；mutation 进行中/失败只作用于被点击的目标行。
- [ ] AC-004：工作台入口页（`/session`）的运行中环境列表对版本错配同样显示待应用提示与行内应用入口，且入口不与环境链接的跳转语义冲突；版本一致时不显示。
- [ ] AC-005：工作台会话页页头、会话详情面板、Profile 详情页非 config 标签的横幅与环境管理列表使用同一待应用判定；版本错配时各自显示、版本相等时各自不显示；三处原有复制表达式不再各自独立判定，无 runtime / 无 `current_config_version` 时均不误报。
- [ ] AC-006：停留在环境管理页且不刷新页面，目标行后端配置版本被抬升并通过 SSE / 查询更新到达后，该行无需导航即从普通运行态转为待应用态，并显示行内应用入口。
- [ ] AC-007：测试覆盖 AC-001 至 AC-006 的表格、卡片、工作台入口与工作台既有路径；项目测试、类型检查与设计门禁通过，既有环境列表/会话测试回归通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试：AC-001/002/003/006 用 `EnvironmentListPage.test.tsx` 注入错配 collection 行与 SSE / cache 更新断言；AC-004 用 `SessionEntryPage.test.tsx`；AC-005 用 `SessionHeader.test.tsx` / `SessionDetailsPanel.test.tsx` / `ProfileDetailPage.test.tsx` 既有断言加共享判定单测；AC-007 为门禁命令回归。

## 上下文区

- 关联 spec：docs/specs/profile_management.md
- 来源：p170（2026-11-23 核实：环境管理列表有版本数据但不判定、不渲染；工作台路径正常；用户裁决统一判定并在行内提供应用并重启）

### 有意不测

- 真实多容器部署下的端到端 SSE 时序：单机单人部署，组件层以 stub 注入事件即可覆盖状态跃迁，不做真实 Docker 栈验证。
- `ConfigTab` 编辑期间是否显示待应用横幅：保持现状，不在本 task 改变该产品的编辑期行为。

### 测试策略

- `EnvironmentListPage.test.tsx`：新增 `current_config_version=2 / runtime.config_version=1` 的错配行，断言表格行与卡片行各自显示待应用提示与行内应用入口；断言版本相等、无 runtime 投影不显示；断言点击应用仅目标行受影响并在完成后提示消失；断言 SSE/cache 更新触发运行态→待应用态无需导航。
- `SessionEntryPage.test.tsx`：错配运行中环境显示待应用提示与应用入口，且链接跳转语义不被破坏。
- 统一判定后保持 `SessionHeader` 已有错配/相等断言，补 `SessionDetailsPanel` / `SharedProfileBanners` 口径一致断言。
- 前端测试、类型检查、设计门禁按 `docs/blueprint/testing.md` 的门禁命令执行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无

### 风险与回退

- 风险：共享判定守卫口径错误导致版本缺失时误报，或 SSE 更新未同步到集合行导致状态不跃迁；行内应用入口与行内其它操作/链接的事件冒泡冲突。
- 回退：本 task 为单实现 commit，失败时 `git revert` 该 commit；不保留运行时开关或双轨判定。

### 依赖与约束

- 复用现有 `useApplyDisplaySettingsMutation` 与 collection/SSE 读模型，不新增后端接口、契约字段或迁移。
- 不破坏 t098 的集合行运行投影口径与「无 runtime 投影显式呈现未知」的既有语义。
- 复用既有 i18n apply pending 文案键，保持 en/zh 键集对齐。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：待应用状态的单一派生口径与各列表/卡片/入口的呈现约定。
- `docs/specs/profile_management.md`：配置版本章节补待应用状态跨界面一致呈现，front matter `tasks` 登记 t106。
