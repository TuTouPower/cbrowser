# Task spec

## 背景

在 Profile「高级」配置面中，多项开关与输入字段在当前运行架构及固定引擎（Linux arm64 `146.0.7680.177.3`，由制品 pin 与摘要确认）下已被证实无效、版本错位或存在解析与边界缺陷：

1. `humanize` 与 `human_preset`：仅在 `runtime_agent/runner.py` 启动进程内对 Playwright context 做客户端动作补丁，而真人交互经 Selkies WebRTC → X11 XTEST、外部自动化经隧道直连回环 CDP，两路均绕过启动端包装；
2. `allow_3p_cookies`（要求 148+）、`transparent_proxy`（要求 151+）与 `portable_cookies`（要求 151+）：在固定 146 二进制 ELF 中均未检出对应 switch 字面量，开关对照测试未体现产品宣称效果；
3. `auto_launch`：全仓无任何自动启动消费点，修改该值仅会生成配置版本并在运行绑定落后时显示待应用；
4. `launch_args`：白名单 22 项中 17 项已存在于 Playwright 默认集合（含桌面路径实际注入的 `--disable-sync`），`--disable-translate` 在固定 ELF 未检出且 Playwright 已通过 `--disable-features` 禁用 `Translate`；`--lang` 优先级依赖 `locale` 与 `geoip` 条件（显式 `locale` 优先；`locale=null` 且 `geoip=true` 时先由首个 `--lang` 提升）；`--mute-audio` 在 146 有头模式实测静音有效；`--disable-blink-features=AutomationControlled` 仅观测到 `navigator.webdriver=false` 一致，未知行为尚待裁决；`ProfileForm.tsx` 按逗号拆分输入还会破坏 `--accept-lang=en-US,en` 等多值参数；
5. `restore_session`：仅在开启时传入 `--restore-last-session`，关闭态在持久化 `Preferences` 已设 `session.restore_on_startup=1` 时仍会恢复页面，而现有文案承诺过强。

依据 `p166`「Codex 评估」中的清理决策及 R1 审阅裁决，本 task 负责删除上述六个无效字段、完成存量 `launch_args` 盘点与退役治理、澄清并保持 `restore_session` 既有行为，并完成前向迁移与真机验收。原 `extension_paths` 盘点、受管 ID 替换、显式扩展权限开关、扩展迁移连续性及自由模式实验从本 task 拆出，由 `p165` 实现 task（`t104`）承接；本 task 保留 `extension_paths` 现行契约不动（对 `--disable-extensions` 的归并仅基于当前默认集）。

## 契约区

### 范围

- **删除六个无效 Profile 字段**：从数据库表、领域模型、API 请求/响应 DTO、路由创建映射、仓储当前行/版本快照/克隆读取、`runtime_agent/runner.py` 严格快照与启动参数、`fingerprint_verification/probe_collector.py` 配置摘要、public/internal OpenAPI、前端生成类型、`profile_field_classification.ts`、表单界面、翻译文案及有效 spec/blueprint/测试夹具中彻底删除 `humanize`、`human_preset`、`auto_launch`、`allow_3p_cookies`、`transparent_proxy`、`portable_cookies`；不保留隐藏兼容字段或动态版本判断。
- **存量行为盘点与退役通用 `launch_args`**：
    - 迁移前对 `profiles` 当前行及全部 `profile_config_versions` 快照执行只读盘点，为当前行和每个历史版本记录有效值与处置分类（至少区分 `冗余`、`等价映射`、`需裁决`）；
    - 确认冗余的 Playwright 默认项与 `--disable-translate` 直接归并（对 `--disable-extensions` 的归并仅建立在当前默认集上，新扩展权限策略由 `t104` 验收）；
    - 若盘点存在有效 `--mute-audio` 使用（或确证需保留静音启动能力），将其迁移至显式「静音启动」字段（默认关闭）；
    - 语言保持单一权威入口（有实际多语言需求时扩展单一模型并统一验证）；有效 `--accept-lang` 列表、GeoIP 模式下提升为 `locale` 的 `--lang`（取首个匹配项；`build_args` 同 key 合并取末项）、超出当前 `locale` 枚举的值，以及行为待定的 `AutomationControlled`，均先确定等价映射或经用户裁决后再移除；
    - 结合已知 API 消费方证据或用户裁决确定是否存在外部脚本在未来独立提交原始参数：确认无独立需求则彻底退役 `launch_args`；仅在确认存在独立需求时采用「小白名单 + 逐条编辑控件」（每条完整传为数组元素，含逗号值可保存、重载和再次编辑）。
- **保持并澄清 `restore_session` 行为**：保留 `restore_session`、`set_google_default`、`clipboard_sync`、`capture_preview`；保留 `restore_session` 现有执行逻辑（关闭态遵循 Chromium 原生启动偏好），更新中英文帮助文案以准确说明边界。
- **前向数据库迁移、在跑环境升级与回退验收**：
    - 新增前向 Alembic revision，先用可恢复数据库备份演练，参照 `0013_profile_identity.py`、`0014_repair_wrapped_snapshots.py` 与 `src/backend/cbrowser/adapters/database/snapshot_identity.py` 共享实现，对平铺及 `{config, proxy_credential_revision}` 包装快照执行 fail-before-write 与幂等重写，保留版本号、运行绑定、代理凭据修订号与 Profile 数据；
    - 明确升级、快照生成与版本选择语义：升级部署保留在跑旧 Browser 实例继续运行（旧实例维持其容器内旧 `snapshot.json`、`runtime_instance_id`、绑定版本 `N` 与 `desired_state=running`）；每当新建或重启实例时，由 Supervisor 在 `/supervisor/v1/profiles/start`（`start_profile`）向 API 读取目标版本不可变配置、经 `ProfileConfig` 校验后写入新实例的 `snapshot.json`；当绑定版本 `N` 不同于当前版本 `N+1` 时，显式指定历史绑定版本 `N` 启动或读取历史快照消费迁移后 `N` 版配置，协调器常规启动/首次新实例/应用并重启采用迁移后 `latest_v = N+1`，克隆读取当前配置并保留源绑定与运行意愿；
    - 明确并验收回退顺序：因 `deploy.sh rollback` 强制 `target_migration == live_stamp`（无降级），跨本次 revision 回退时须先停止新版写入、恢复升级前数据库备份/恢复点至旧 stamp，再按匹配的旧 `release` 与 `compose.yaml` 启动旧版并通过 readiness 验收；
    - 同步更新受影响的 spec、blueprint、契约测试与固定引擎真实部署验收。

### 非范围

- 扩展能力的受管资产替换（`extension_paths` 盘点、受管 ID 替换、显式扩展权限开关、Chromium 扩展 ID 连续性迁移与自由模式入口实验）：已拆出由 `p165` 实现 task `t104` 承接，本 task 保留当前 `extension_paths` 契约不动。
- 未来按调用显式触发的客户端拟人化执行（归属实际发送动作的 `agent_executor` 或外部 CDP 客户端调用侧，不在 Profile 静态配置保留或新增开关）。
- 未经批准与真机验证的 Chromium 148+/151+ 特性与原生 Chrome 界面本地化（若需原生本地化须作为新增产品契约单独验证镜像资源、启动选取与控件）。
- Alembic downgrade（仅向前迁移）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：六个已证实无效的字段（`humanize`、`human_preset`、`auto_launch`、`allow_3p_cookies`、`transparent_proxy`、`portable_cookies`）在数据库模型、领域模型、API 响应、导出契约、运行时配置快照、指纹探针摘要及管理表单与翻译中彻底移除；向环境创建或更新接口提交任一已删除字段时，按严格契约返回 422 校验错误。
- [ ] AC-002：迁移前对当前行与全部历史配置版本快照完成只读盘点，为当前行和每个历史版本记录有效值与处置（至少区分冗余、等价映射、需裁决）；存在未解决项时迁移阻断并断言 DB schema、业务行与快照零改写；对带 `--mute-audio` 的当前行和历史快照验证迁入开启态，对无静音旧版本和新建环境验证默认关闭；语言夹具覆盖显式 `locale`、`locale=null` 配合 `geoip` 开关、多值 `--accept-lang`、重复项（GeoIP 提升取首匹配、同键合并取末项）与超枚举项，且明确记录 `AutomationControlled` 与外部 API 消费需求裁决；若完全退役则创建/更新传 `launch_args` 键返回 422，若确证独立需求保留小白名单则 `launch_args` 键合法、已撤回数组项返回 422 且合法含逗号值经实际表单保存、读取、再编辑后数组完整不变。
- [ ] AC-004：以旧 release 真实 schema stamp 构造升级库（涵盖平铺/包装快照及损坏或未解决数据），验证发现阻断项零业务写入，且注入 DDL/DML 中途故障时 schema、行、快照与 `alembic_version` stamp 一并回退；迁移后保留配置版本标识、绑定版本、`proxy_credential_revision` 与用户数据，再跑 `upgrade head` 及独立重算盘点/变换无漂移；以绑定 `N` ≠ 当前 `N+1` 对照验证升级接管（保留旧实例运行与 `N < N+1` 待应用）、Supervisor 新建实例向 API 拉取指定版本写 `snapshot.json`（含显式 `N` 版本启动与读取、协调器常规最新/应用重启选 `N+1`）及仅配置/含状态克隆后的运行意愿与绑定一致性。
- [ ] [deploy] AC-005：在固定目标浏览器引擎的真实有头容器拓扑中验证保留项行为：语言以 Web 主语言与有序回退规则验收（`en-US` → HTTP `Accept-Language: en-US,en;q=0.9`、`navigator.languages` 为 `["en-US"]`；`zh-CN` → `zh-CN,zh;q=0.9`、`["zh-CN"]`），并明确记录内置界面保持英文的原生边界；以同一确定音源和同一音频监测端正负对照验证迁移开启态静音输出全零与默认关闭态有声；以两个带标记标签对照 `restore_session` 开/关 × 原生 `Preferences` 恢复开/关的四格行为并确认中英文帮助文案与之一致。
- [ ] [deploy] AC-007：在隔离真实部署拓扑中执行旧版→新版 release 升级、在跑环境接管（旧实例保持运行，重启或应用变更后切至新版镜像与新 `snapshot.json`）与跨 revision 回退演练（先停新版写入并恢复迁移前数据库备份至旧 stamp，再按匹配旧 release 与 `compose.yaml` 启动旧版并通过 readiness 验收），确认旧 stamp、数据与 Profile 可用。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001、AC-002 与 AC-004 可通过前后端单元测试、OpenAPI/生成类型门禁、合成迁移与故障回滚测试及 API/Supervisor 集成测试自动验证。
- `[deploy]` AC-005 与 `[deploy]` AC-007 须在本地 OrbStack 真实 Docker、固定有头目标引擎与隔离 release 部署演练中执行并留证，不得以 mock 或仅检查启动命令行代替。

## 上下文区

- 关联 spec：docs/specs/profile_management.md
- 受影响 spec：`docs/specs/fingerprint_platform.md`、`docs/specs/storage_and_artifacts.md`、`docs/specs/ui_design_system.md`、`docs/specs/release_deployment.md`（若升级或回退操作契约存在新增表述时同步更新）。
- 来源：`p166`（2026-11-22 Codex 评估与 `review_r1.md` R1 审阅结论：独立交付六字段清理、`launch_args` 盘点退役与 `restore_session` 行为澄清；原 `AC-003`、`AC-006`、`extension_paths` 盘点/替换/迁移及自由模式实验已拆分移交 `p165` 实现 task [`t104`](../t104_managed_extensions_and_bitwarden_passkey/task.md) 承接）。

### 有意不测

- 跨机器与跨操作系统加密后端下的真实登录会话迁移：当前部署基线限定为单机 OrbStack Linux arm64。
- 未来客户端按调用显式拟人化执行、Chromium 148+/151+ 高版本内核开关及原生 Chrome 界面本地化。
- 受管扩展资产库、扩展 ID 连续性迁移与四态/自由模式验收（由 `t104` 承接）。

### 测试策略

- **盘点与迁移测试**：以旧 release 真实 schema stamp 构造包含平铺与 `{config, proxy_credential_revision}` 包装快照、全部 17 项冗余、`--disable-translate`、`--mute-audio`、`--accept-lang` 多值、GeoIP 提升 `--lang`、重复语言项、超枚举语言、`AutomationControlled`、损坏 JSON 与未解决阻断项的合成库；分别验证 fail-before-write 零写入、DDL/DML 中途故障整体回滚、`upgrade head` 幂等与变换重算零漂移；覆盖 `N` vs `N+1` 升级接管、Supervisor 写 `snapshot.json`、历史版本读取与克隆。
- **契约与 UI 测试**：逐个提交 6 个已删除字段断言 422 指向对应字段且创建/更新零写入；按最终退役或小白名单分支分别测试 422 边界及含逗号参数值的保存/读取/再编辑完整链路；验证 OpenAPI 与前端生成类型及 `profile_field_classification.ts` 一致。
- **真实引擎与发布演练**：在隔离真实拓扑验收 Web 语言主备规则（及内置页原生边界记录）、确定音源/监测端静音正负对照、`restore_session` 2×2 四格与双标签观测，以及旧版→新版升级、在跑实例接管与停写→恢复旧库→按旧 release 启动的回退全流程。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 存量数据库 `launch_args` 分布与外部 API 消费情况（含 `--mute-audio`、`--accept-lang`、GeoIP 提升 `--lang`、超枚举语言、`AutomationControlled` 及是否仍存在独立原始参数提交需求）：`UNVERIFIED-SPIKE`，在动表结构前运行只读分类盘点并核查已知 API 消费方，确定退役方案或小白名单备选以及需用户裁决的等价映射后回填结论再实施。

### 风险与回退

- 风险：旧版本快照残留已删除 key 会触发 `ProfileConfig(extra="forbid")` 拒绝启动或克隆；SQLite `transactional_ddl=False` 若未严密控制 DDL/DML 顺序与失败回滚机制可能导致半迁移态；跨 revision 回退受 `deploy.sh rollback` 的 stamp 等式门禁约束，不能直接跳过恢复数据库。
- 回退：迁移前完成在线 DB 备份（及无写者时可选环境恢复点）演练；盘点或迁移校验发现阻塞项则零写入中止；若新版本上线后须回退，按顺序先停止新版写入、恢复升级前数据库备份至旧 stamp，再按匹配的旧 `release` 与 `compose.yaml` 启动旧版并通过 readiness 验收，不保留运行时双读降级。

### 依赖与约束

- 与 `t104` 共享 `profiles` 表、领域模型、`runner.py` 与 Alembic head；已确定串行调度，由本 task 先行完成并收敛 Alembic head，`t104` 声明 `depends_on: t103`。
- 严格遵循 `AGENTS.md` 开发铁律（零兼容性负担）与 `docs/blueprint/conventions.md`（迁移只向前、fail-before-write、Alembic 单一 head、OpenAPI 与前端类型只由脚本生成）。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：更新第 5.5 节等处现行 `launch_args` 严格加载说明，避免长文继续承诺已退役的能力。
- `docs/blueprint/security.md`：更新第 162 行等处现行 `launch_args` 严格加载与拒绝说明。
- `docs/blueprint/domain.md`：移除六个无效字段与退役 `launch_args`（或记录备选小白名单/显式静音启动语义），补充 `restore_session` 与原生偏好优先级契约及本次迁移规则。
- `docs/blueprint/browser_runtime.md`：更新 Runner 启动参数边界、Web 语言/静音/`restore_session` 实测语义与内置界面边界。
- `docs/blueprint/persistence.md`：更新 `profiles` 表字段清单与新增前向迁移修订说明。
- `docs/blueprint/testing.md`：补充六个无效字段 422、盘点迁移原子性/幂等、真实 146 引擎行为与发布升级/回退演练门禁。
