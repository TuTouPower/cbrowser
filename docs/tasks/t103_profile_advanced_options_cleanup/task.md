# Task spec

## 背景

在 Profile「高级」配置面中，多项开关与输入字段在当前运行架构及固定引擎（Linux arm64 `146.0.7680.177.3`）下已被证实无效、版本错位或存在解析与边界缺陷：

1. `humanize` 与 `human_preset` 在启动端仅对本进程 Playwright context 打客户端动作补丁，而真人交互经 Selkies WebRTC → X11 XTEST、外部自动化经隧道直连回环 CDP，两路均绕过启动端包装；
2. `allow_3p_cookies`（要求 148+）、`transparent_proxy`（要求 151+）与 `portable_cookies`（要求 151+）在固定 146 二进制未检出对应 switch 字面量且开关对照未体现产品宣称效果；
3. `auto_launch` 全仓无任何自动启动消费点，仅生成配置版本并触发待应用提示；
4. `launch_args` 白名单 22 项中 17 项已在 Playwright 默认集合（含桌面路径实际注入的 `--disable-sync`），`--disable-translate` 在固定 ELF 未检出且 Playwright 已禁用 `Translate`，`--lang` 优先级依赖 `locale` 与 `geoip` 条件，`ProfileForm` 按逗号拆分输入还会破坏 `--accept-lang=en-US,en` 等多值参数；同时 `extension_paths` 缺少容器资产映射与权限开关，而 `restore_session` 在原生首选项已开启恢复时仍会恢复页面。

依据 `p166`「Codex 评估」中的清理决策，本 task 以零兼容性负担彻底清理上述无效配置、按存量行为盘点退役通用 `launch_args`、将扩展能力收归 `p165` 受管资产与显式权限，并落实原子迁移与真实引擎验收。

## 契约区

### 范围

- **删除六个无效 Profile 字段**：从数据库表、领域模型、API 请求/响应 DTO、路由创建映射、仓储当前行/版本快照/克隆读取、`runtime_agent/runner.py` 严格快照与启动参数、`fingerprint_verification/probe_collector.py` 配置摘要、public/internal OpenAPI、前端生成类型、`profile_field_classification.ts`、表单界面、翻译文案及有效 spec/blueprint/测试夹具中彻底删除 `humanize`、`human_preset`、`auto_launch`、`allow_3p_cookies`、`transparent_proxy`、`portable_cookies`；不保留隐藏兼容字段或动态版本分支。
- **存量行为盘点与退役通用 `launch_args`**：
    - 迁移前对 `profiles` 当前行及全部 `profile_config_versions` 快照执行只读分类并输出受影响 Profile 与版本清单；
    - 确认冗余的 Playwright 默认项与 `--disable-translate` 直接归并移除；
    - 若盘点或真实使用确认存在有效 `--mute-audio` 需求，将其迁移至显式「静音启动」布尔字段（默认关闭）；
    - 语言维持单一权威配置入口；有效 `--accept-lang` 列表、GeoIP 模式下提升为 `locale` 的 `--lang`（取首个匹配项；`build_args` 同 key 合并取末项）、超出当前 `locale` 枚举的值，以及行为存疑的 `--disable-blink-features=AutomationControlled`，均先完成等价映射或经用户裁决后再移除；有实际多语言需求时扩展单一语言模型并统一验证原生语言、HTTP 请求头与 `navigator.languages`；
    - 仅在存量盘点确认已有 API 或工作流确实依赖独立原始参数时，才采用「小白名单 + 逐条编辑控件」（每条完整传为数组元素，不按逗号拆碎）备选方案；否则彻底退役 `launch_args`。
- **澄清 `restore_session` 行为边界**：保留 `restore_session`、`set_google_default`、`clipboard_sync`、`capture_preview` 四个有效高级选项；明确并验证 `restore_session` 关闭态与持久化 `Preferences` 中 `session.restore_on_startup=1` 的优先级契约。
- **扩展归 `p165` 受管资产与显式权限**：
    - 扩展能力专由 `p165` 的受管扩展资产与显式扩展权限开关负责，不留存在 `launch_args` 或原始宿主路径 `extension_paths`；
    - 在 `p165` 受管资产就位前提下以受管 ID 替换原始 `extension_paths`，默认关闭态既禁用扩展系统也不传显式加载目录，开启态解析白名单资产并只读挂载；
    - 迁移前盘点存量 `extension_paths`：能对应 `p165` 受管资产的路径明确迁移，无法映射的非空路径先列清单阻断升级，禁止无声丢失已加载扩展。
- **前向数据库迁移与全链路验收**：
    - 新增前向 Alembic revision，先以可恢复数据库备份演练，沿用 `0013_profile_identity.py` 的 fail-before-write 与内外层快照重写模式原子迁移 `profiles` 与全部版本快照，保留配置版本号、运行绑定、代理凭证修订号与浏览器用户数据文件；
    - Supervisor 为新启动或升级后的实例从迁移后的绑定版本重写 `snapshot.json`；
    - 同步更新受影响的 spec、blueprint、契约测试与固定引擎实测。

### 非范围

- 未来按调用显式触发的拟人化执行（归属实际发送动作的 `agent_executor` 或外部 CDP 客户端调用侧，不在 Profile 静态配置保留或新增开关）。
- 未经批准与真机验证的 Chromium 148+/151+ 特性（如高版本第三方 Cookie、透明代理或便携 Cookie 开关）。
- `p165` 受管扩展资产库自身的上传、解包、元数据提取与 UI 资产管理建设（若拆出独立前置 task，由该前置 task 交付后供本 task 替换 `extension_paths`；若与 `p165` 协同实施，则须在满足前置契约后一并验收）。
- Alembic downgrade（仅向前迁移）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：六个已证实无效的字段（`humanize`、`human_preset`、`auto_launch`、`allow_3p_cookies`、`transparent_proxy`、`portable_cookies`）在数据库模型、领域模型、API 响应、导出契约、运行时配置快照、指纹探针摘要及管理表单与翻译中彻底移除；向环境创建或更新接口提交任一已删除字段时，按严格契约返回 422 校验错误。
- [ ] AC-002：实施迁移前能对现有 `profiles` 行与全部历史配置版本快照完成只读分类盘点并输出受影响条目清单；通用 `launch_args` 按盘点裁决完成退役（若存在有效静音需求则提供显式默认关闭的「静音启动」字段，语言保持单一权威入口；仅在确认独立工作流刚需时保留小白名单与逐条数组编辑控件，且含逗号参数值经保存、重载和再编辑均完整无拆碎）；向接口提交已退役参数键返回 422 校验错误。
- [ ] AC-003：扩展权限与配置收归受管资产体系：由显式扩展权限开关与受管扩展 ID 替换原始 `extension_paths`；存量非空 `extension_paths` 在迁移前完成盘点，可映射条目明确迁至受管 ID、无法映射条目先列清单阻断写入而不无声丢失；默认关闭态既禁用扩展系统也不传递显式加载路径。
- [ ] AC-004：前向迁移先经可恢复备份演练，对混合形状与包装格式的版本快照执行 fail-before-write 前置校验后原子升级 `profiles` 与全部 `profile_config_versions` 快照，保留配置版本号、当前运行绑定、代理凭证修订号与浏览器用户数据；Supervisor 为新实例从迁移后绑定版本重写运行期快照；在跑环境升级、重启、历史版本读取及仅配置/含状态克隆全部成功，重复执行迁移保持幂等。
- [ ] [deploy] AC-005：在固定目标浏览器引擎的真实有头容器拓扑中，验证有效行为保持与新契约一致：若启用「静音启动」则音频监测端实测全零且默认关闭时有声；单一权威语言配置在原生浏览器界面语言、HTTP 请求头与 `navigator.languages` 三处一致；`restore_session` 开关及其与持久化原生首选项的既定优先级契约与实测相符。
- [ ] [deploy] AC-006：在固定目标浏览器引擎的真实有头容器拓扑中验证扩展四态与自由模式：默认关闭态既不运行扩展也不加载存量扩展；开启并指定受管扩展时仅只读挂载并执行白名单扩展；曾开启后改回关闭态时既有扩展停止执行；两个加载不同扩展的 Profile 相互隔离不串用；同步验证自由模式下的实际扩展安装入口。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001 至 AC-004 可通过前后端单元测试、OpenAPI/类型导出门禁、迁移幂等与阻断测试及隔离 API/Supervisor 集成测试自动验证（其中备选小白名单 UI 与受管扩展替换在无真实引擎层覆盖边界，真实运行时效果由 AC-005/AC-006 承担）。
- `[deploy]` AC-005 与 AC-006 须在本地 OrbStack 真实 Docker 与固定有头目标引擎拓扑中执行音频、语言、会话恢复及扩展四态实测留证，不得以 mock 或仅检查启动命令行代替真实运行时验证。

## 上下文区

- 关联 spec：docs/specs/profile_management.md
- 受影响 spec：`docs/specs/fingerprint_platform.md`、`docs/specs/storage_and_artifacts.md`、`docs/specs/browser_isolation.md`、`docs/specs/ui_design_system.md`
- 来源：`p166`（2026-11-22 Codex 评估与固定 arm64 `146.0.7680.177.3` 真机对照确认六个无效字段、17/22 `launch_args` 冗余与逗号拆分缺陷、`restore_session` 原生优先级、`extension_paths` 与 `--disable-extensions` 交互及跨全仓清理影响面）；关联 `p165`（受管多扩展资产与显式扩展权限方案）。

### 有意不测

- 跨机器与跨操作系统加密后端下的真实登录会话迁移：当前部署基线限定为单机 OrbStack Linux arm64，不在跨宿主环境测试。
- 未来客户端按调用显式拟人化执行与 Chromium 148+/151+ 高版本内核特性：不在当前固定 146 制品范围内测试。

### 测试策略

- **盘点与迁移测试**：构造覆盖冗余项、有效 `--mute-audio`、有效 `--accept-lang`、GeoIP 提升 `--lang`、重复语言项、超枚举语言、`AutomationControlled`、可映射与不可映射 `extension_paths`、以及平铺与 `{config, proxy_credential_revision}` 包装快照的合成库；TDD 验证 fail-before-write 阻断、原子重写、版本号/代理凭据修订号保留、重复执行幂等与备份恢复演练。
- **契约与 UI 测试**：验证删除字段与退役字段触发 422、OpenAPI 与前端生成类型及 `profile_field_classification.ts` 一致、表单不再展示六个无效字段（及已退役输入）；若保留备选小白名单，补充逐条编辑保存/重载/再编辑含逗号参数测试。
- **真实引擎容器验收**：在隔离部署实例中分别验证：1）音频监测端静音对照；2）原生语言、HTTP `Accept-Language` 与 `navigator.languages` 一致性；3）`restore_session` 开关与 `Preferences` 优先级；4）扩展默认关闭/开启加载/开启后关闭/双 Profile 隔离/自由模式安装入口；5）在跑环境升级与绑定版本重启。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 存量生产/本地数据库中 `launch_args` 与 `extension_paths` 的实际使用分布（含 `--mute-audio`、`--accept-lang`、GeoIP 提升 `--lang`、超枚举语言、`AutomationControlled` 及非空 `extension_paths`）：`UNVERIFIED-SPIKE`，在实施任何迁移前对可恢复数据库副本运行只读分类盘点脚本输出受影响 Profile 与版本；若发现需要等价映射裁决或独立原始参数刚需的条目，在改写前交由用户裁决后再收敛方案。
- `restore_session=false` 与 `Preferences` 中 `session.restore_on_startup=1` 冲突时的产品优先级语义：`UNVERIFIED-SPIKE`，需明确关闭态是否主动写入偏好覆盖或仅不传 `--restore-last-session` 并更新表单说明，随后在固定 `146.0.7680.177.3` 上实测验证。
- `p165` 自由模式下固定 `146.0.7680.177.3`（`ungoogled-chromium`）的实际扩展安装入口：`UNVERIFIED-SPIKE`，需在去掉 `--disable-extensions` 后实测商店页、本地 `.crx` 拖入或开发者模式加载表现。
- `p165` 受管扩展资产基础设施（资产存储、校验与容器只读挂载）尚未立项交付：`UNVERIFIED-BLOCKING`，须与 `p165` 协同立项先行交付受管资产能力或在启动前明确合并范围并登记前置依赖后，方可解除阻塞执行 `extension_paths` 替换与 AC-003/AC-006。

### 风险与回退

- 风险：旧版本快照残留已删除 key 会触发 `ProfileConfig(extra="forbid")` 拒绝启动或克隆；直接删弃 `launch_args` 或 `extension_paths` 可能无声丢失存量行为（语言、静音或已加载扩展）；在跑环境若未由 Supervisor 重写 `snapshot.json` 将与新 Runner 契约失配。
- 回退：迁移前按恢复点与数据库备份规范完成可恢复备份演练；一旦迁移前阻塞清单命中未映射条目则不写库直接中止；若发布后发现行为回归，通过 release 回退与备份恢复还原程序版本和旧库，不保留运行时双读降级。

### 依赖与约束

- **扩展前置约束**：扩展资产目录、校验与只读挂载契约归口 `p165`；进入实施阶段（`start`）前须先确立 `p165` 前置 task 并在 `progress.md` 登记 `depends_on`（或经用户明确合并 `p165` 交付边界）。
- **项目硬约束**：严格遵循 `AGENTS.md` 开发铁律（零兼容性负担）与 `docs/blueprint/conventions.md`（迁移只向前、fail-before-write、Alembic 单一 head、受管存储由 `MountPlanner` 构造、OpenAPI 与前端类型只由脚本生成）；`docs/specs/` 对应规范、`docs/blueprint/` 及旧测试断言须同批收敛。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：移除六个无效字段与通用 `launch_args`（或记录备选小白名单/显式静音启动语义）、记录 `restore_session` 优先级边界、对齐 `p165` 受管扩展 ID 引用及本轮前向迁移契约。
- `docs/blueprint/browser_runtime.md`：更新 Runner 启动参数边界、扩展关闭/受管加载规则及 `restore_session` 实测语义。
- `docs/blueprint/persistence.md`：更新 `profiles` 表字段清单与新增前向迁移修订说明。
- `docs/blueprint/testing.md`：补充删除字段 422、盘点迁移幂等与阻断及固定 146 引擎静音/语言/扩展四态真实验收要求。
