# Task spec

## 背景

用户 2026-11-23 反馈：修改配置后停留在「环境管理」页（`EnvironmentListPage`，路由 `/`），行徽章仍是「运行中」，必须进入工作台具体会话页（`SessionPage`，路由 `/session/:profileId`）才看到「有待应用配置 / 应用并重启」提示。核实：判定「配置变更待应用」的唯一机制是 `runtime.config_version !== profile.current_config_version`，该表达式只写在工作台/详情 3 个组件内；`EnvironmentListPage` 的 collection 行已同时携带两个版本字段，但从不比较；工作台入口页 `SessionEntryPage` 同样漏判。

架构复核结论：t098 统一了数据（runtime 投影并入 collection 行），但没有统一语义。「运行实例配置已过期」是领域事实，却仍以原始版本比较式散落在视图层，任何新 surface 都能再次漏判；三处守卫互不一致，连「何时算待应用」都没有领域定义；`shared/presentation.ts:7-12` 自称展示语义唯一来源却没有待应用条目；apply 复合命令与 profile 作用域守卫在多个组件复制。按开发铁律，修复必须把事实提升为读模型一等字段、把动作收敛为单一命令，而不是共享一个“记得调用”的 helper。用户裁决：行内提供「应用并重启」，不用来回跳转。

## 契约区

### 范围

- 在领域层定义唯一 `config_pending` 谓词：runtime 存在、`observed_state != "stopped"` 且 `current_config_version > runtime.config_version` 时为真；停止态、无 runtime、版本相等、元数据或 `capture_preview` 变更时为假。终态 error（实例已释放但仍非停止态）保持为真，以便用户用新版本恢复。不改任何版本抬升规则。
- 把 `config_pending: bool` 作为只读派生事实加入 `ProfileRuntimeProjection`、`ProfileRuntimeResponse`、`ProfileRuntimeStatusEvent` 三个读模型，分别由 collection 行构造、`make_runtime_response`、SSE 初始快照与实时发布填入；不写 DB、不新增存储列。
- 破坏性更新 `schemas/openapi/cbrowser_v1.json` 与 `cbrowser_internal.json`，重新生成 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`；`types.ts` 别名自动生效，`check:api` 通过。
- 前端彻底删除三处（及全仓）「待应用 = 两版本比较」的视图层判定，`SessionHeader` / `SessionDetailsPanel` / `SharedProfileBanners` 统一读 `runtime.config_pending`。
- 在 `shared/presentation.ts` 增加待应用 descriptor，并由一个共享呈现单元在表格、卡片、工作台入口、会话页头、会话详情复用，杜绝各 surface 自拼文案/图标。
- 环境管理列表（表格 + 卡片）每行显示待应用状态并提供行内「应用并重启」入口；工作台入口页一致显示且不破坏环境链接跳转语义。
- apply 动作收敛到单一命令边界：以现有 `useApplyDisplaySettingsMutation`（stop + 等待 + 以新版本启动 + 收敛等待）为唯一实现，内部统一经 `scopeMutationToProfile` 提供 profile 作用域的 pending/error；所有 surface 薄调用，不再各自读原始 mutation state。
- 停留在环境管理页不刷新时，SSE `runtime_state` 携带 `config_pending` 到达后目标行无需导航即从普通运行态转为待应用态。
- 测试与文档：补领域谓词单测、契约比对、前端各 surface 断言；`docs/specs/profile_management.md` 记录待应用状态为读模型派生事实并登记 t106。

### 非范围

- 不做配置变更自动应用/自动重启：保留「用户控制重启时机」的产品契约，不改变现有 apply 语义。
- 不新增 apply 后端接口或新网络动作；不把 `config_pending` 写成持久列，不做双写。
- 不保留双轨判定、feature flag 或前端版本比较兼容分支（零兼容性负担）。
- 不改元数据 / `capture_preview` / 同值提交不生成版本的版本三分规则，不改 SSE 事件信封与订阅机制。
- 不改 `ConfigTab` 编辑期是否显示待应用横幅的现有行为。
- 不做大规模文案重设计，复用既有 apply pending 文案键。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：领域层唯一 `config_pending` 谓词在 runtime 存在、`observed_state != "stopped"` 且当前配置版本高于运行版本时为真；停止态（实例已释放）、无 runtime、版本相等、仅元数据或仅 `capture_preview` 变更时为假；终态 error 仍为真；前端与各 surface 不再自行比较版本得出待应用。
- [x] AC-002：`config_pending` 随 `ProfileRuntimeProjection`（collection 行）、`ProfileRuntimeResponse`、`ProfileRuntimeStatusEvent`（SSE data）三个读模型交付；`cbrowser_v1.json` / `cbrowser_internal.json` 与生成 `d.ts` 同步，`check:api` 通过；该字段为只读派生事实，库中无对应存储列。
- [x] AC-003：`GET /api/v1/profiles/collection` 的行在 `runtime.config_pending` 为真时，环境管理表格该行显示待应用提示；为假或该行无 runtime 投影时不显示，且无 runtime 投影仍呈现显式未知态。
- [x] AC-004：卡片布局按同一 `config_pending` 与同一呈现单元显示或不显示待应用提示，与表格布局不存在口径漂移。
- [x] AC-005：表格与卡片的待应用行提供行内「应用并重启」入口；点击后仅目标环境经历停止并以新版本运行，应用完成后该行待应用提示消失，其它行不受影响；mutation 进行中/失败只作用于被点击的目标行。
- [x] AC-006：工作台入口页（`/session`）的运行中环境列表对 `config_pending` 为真的行一致显示待应用提示与行内应用入口，入口不与环境链接跳转语义冲突；为假时不显示。
- [x] AC-007：`SessionHeader`、`SessionDetailsPanel`、`SharedProfileBanners` 读 `runtime.config_pending`，在版本错配、版本相等、停止态三种情形下与列表口径一致；全仓视图层无残留的「待应用 = 版本比较」表达式。
- [x] AC-008：停留在环境管理页且不刷新、不导航，目标行 SSE `runtime_state` 带 `config_pending=true` 到达后，该行无需导航即从普通运行态转为待应用态并显示行内应用入口。
- [x] AC-009：测试覆盖 AC-001 至 AC-008（领域谓词、三个读模型填充、契约导出、表格/卡片/入口/会话各 surface、SSE 跃迁、profile 作用域守卫）；项目测试、类型检查与设计门禁通过，既有环境列表/会话测试回归通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试：AC-001 用领域层单测覆盖谓词真值表；AC-002 用契约导出比对与 `check:api`；AC-003/004/005/006/008 用 `EnvironmentListPage.test.tsx` / `SessionEntryPage.test.tsx` 注入 SSE 与 mutation 断言；AC-007 用 `SessionHeader.test.tsx` 等既有断言加全仓 grep；AC-009 为门禁命令回归。

## 上下文区

- 关联 spec：docs/specs/profile_management.md
- 来源：p170（2026-11-23 核实环境管理列表有版本数据但不判定/不渲染；同日架构复核升级为「领域派生事实入读模型 + 单一命令」，用户裁决行内提供应用并重启）

### 有意不测

- 真实多容器部署下的端到端 SSE 时序：单机单人部署，组件层以 stub 注入事件即可覆盖状态跃迁，不做真实 Docker 栈验证。
- `ConfigTab` 编辑期间是否显示待应用横幅：保持现状，不在本 task 改变该产品的编辑期行为。

### 测试策略

- 后端单测：谓词真值表（starting/running/stopping/error 为真候选、stopped 与无 runtime 为假、版本相等、元数据与 `capture_preview` 不变版本）；断言三个读模型填充同一谓词结果，库表无新增列。
- 契约：重新导出两个 OpenAPI，跑 `npm run check:api`，断言生成 `d.ts` 含 `config_pending` 且手写别名无残留比较式。
- `EnvironmentListPage.test.tsx`：按 `runtime.config_pending` 驱动表格/卡片显示、行内应用仅作用于目标行、SSE/cache 更新触发运行态→待应用态无需导航。
- `SessionEntryPage.test.tsx`：待应用提示应用入口与链接语义共存。
- `SessionHeader.test.tsx` / `SessionDetailsPanel.test.tsx` / `ProfileDetailPage.test.tsx`：三态口径一致，既有断言迁移到读模型字段而非就地改预期。
- 前端测试、类型检查、设计门禁按 `docs/blueprint/testing.md` 的门禁命令执行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无

（谓词边界已核实：`repository.py:1236` 绑定实例时置 `starting`；`repository.py:1373` 进入 `stopped` 时清空 `runtime_instance_id`；`repository.py:1349,1374` 终态 error 释放实例但 `observed_state` 仍为 `error`。故以 `observed_state != "stopped"` 判定非停止态，并写入谓词单测真值表，不再有未核实外部契约。）

### 风险与回退

- 风险：谓词边界误判导致停止态误报或运行中漏报；契约字段新增后旧前端与新后端错配；行内应用入口与行内其它操作/链接的事件冒泡冲突。
- 回退：本 task 为单实现 commit，失败时 `git revert` 该 commit；不保留运行时开关或双轨判定。

### 依赖与约束

- `config_pending` 为只读派生事实，不写 DB、不改变版本抬升、SSE 信封或订阅机制；两个 OpenAPI 与生成类型必须同批更新。
- 破坏性变更：删除全部前端版本比较式与各自为政的 mutation state 读取，不保留兼容分支。
- 复用既有 `useApplyDisplaySettingsMutation` 与 `scopeMutationToProfile`，由单一命令 hook 结构性满足 `docs/specs/profile_management.md:75` 的 profile 隔离要求。
- 复用既有 i18n apply pending 文案键，保持 en/zh 键集对齐。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：待应用为领域派生事实、谓词边界与版本三分的关系。
- `docs/blueprint/architecture.md`：读模型派生事实的统一填充点与 SSE 携带方式。
- `docs/blueprint/frontend.md`：待应用状态单一呈现单元与单命令边界，删除各 surface 自拼装口径。
- `docs/blueprint/decisions/`：新增 ADR 记录「待应用事实入读模型、视图零比较」的决定与理由。
- `docs/specs/profile_management.md`：配置版本章节补待应用读模型口径，front matter `tasks` 登记 t106。
