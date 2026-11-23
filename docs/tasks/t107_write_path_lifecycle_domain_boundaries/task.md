# Task spec

## 背景

p167 来自 t104 收尾的 review minor（`t104_code_f011/f012`），原描述是「拆分 6 个 `CC>=15` 后端函数」。核实当前 main：5 个函数仍在阈值以上（`profile_service.update_profile` CC 24、`repository.update_profile` CC 21、`_match_legacy_entry` CC 19、`supervisor.core.start_profile` CC 37、`restore_point` CC 35），`manifest.extract_directory_metadata` 已降至 14，剔除。

高 CC 是症状，不是根因。根因是领域决策没有边界：Profile 写路径把 patch 归一化、平台/字体重绑、引用校验、扩展校验、错误翻译揉在一个方法里；Repository 用手工 25 字段清单把 `ProfileConfig` 复制到 ORM，形成与模型平行的第二份契约；Supervisor 启动与恢复点把生命周期状态机和回滚协议写成直线命令式代码；扩展身份匹配把分类规则写成条件树。t104 每次新增能力只能继续往这些分支树里塞条件。按铁律，本 task 以「补领域边界」而非「降 CC 数字」为目标，对外行为与契约一律不变。

## 契约区

### 范围

- `ProfileService.update_profile`：把 patch 决策提升为显式更新计划——归一化、平台/字体重绑决策、引用校验、扩展校验、错误翻译各自成为可独立调用的单元；编排方法只推进阶段，不承载业务判断。
- `ProfileRepository.update_profile`：拆分为幂等审计重放、config→ORM 单一投影、版本跃迁决策、快照写入、审计写入；删除与 `ProfileConfig` 平行的手工字段赋值清单，改由模型驱动投影覆盖全部配置字段。
- `supervisor/core.py start_profile`：提取显式启动生命周期阶段（锁获取、陈旧会话清理、force 重置、意图与阻塞校验、实例绑定、目录/凭证装配、容器启动、观察收敛、失败收尾），每阶段单一职责，编排只推进 phase 与回滚。
- `extension_paths_migration._match_legacy_entry`：身份分类改为规则表/策略驱动，保留精确匹配、核心哈希匹配、歧义与缺失四类结论的现有文案。
- `scripts/restore_point.py restore_point`：提取恢复事务阶段（完整性校验、陈旧清扫、暂存与校验、journal、原子切换、回滚），编排只推进 phase。
- 清理 `tests/unit/test_t075_supervisor_fonts.py:165` 的 `# type: ignore[method-assign]` mock 写法，保持断言不变。

### 非范围

- 不改任何对外 API、OpenAPI、DB schema、Alembic 迁移或错误码/文案。
- 不改配置版本抬升规则、幂等键语义、运行状态机对外表现与恢复点文件格式。
- 不重构未被 p167 点名且本 task 无行为增量的函数（如 `create_profile`、`create_app`、`runner.start`）。
- 不新增依赖、feature flag、兼容 wrapper 或双轨路径；旧胖函数直接删除。
- 不重构已降至 `CC<15` 的 `manifest.extract_directory_metadata`。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Profile 更新的既有行为完全不变——元数据与 `capture_preview` 不生成新版本、运行配置变更抬升版本并写快照、同值提交不抬升、平台切换重绑字体集且无可用集时失败封闭、分组/代理引用校验、扩展白名单校验、幂等重放与异常映射——全部由既有测试回归通过，API 响应与错误形状无变化。
- [ ] AC-002：Supervisor 启动的既有行为不变——幂等启动、force 重置、阻塞与意图校验、陈旧会话清理、实例绑定、容器装配、观察收敛、失败收尾与清理——既有单元与 E2E 回归通过，无新增或缺失阶段。
- [ ] AC-003：恢复点的既有行为不变——清单校验、schema stamp 核对、陈旧暂存清扫、空间不足拒绝、暂存校验、journal 与原子切换、失败回滚、中断恢复提示——既有测试回归通过，恢复点文件格式与退出码不变。
- [ ] AC-004：旧 `extension_paths` 迁移的身份分类结论不变——精确匹配、核心哈希匹配、歧义、缺失四类结论与文案逐项回归通过。
- [ ] AC-005：写路径的三类校验（平台/字体绑定、分组与代理引用、扩展白名单）各自可独立调用并单独断言；`update_profile` 编排方法不再内联这些判断分支。
- [ ] AC-006：`ProfileConfig` 与 ORM 列之间存在单一投影，测试断言全部配置字段均被覆盖；新增或删除配置字段时不再需要手工同步第二份字段清单。
- [ ] AC-007：Supervisor 启动与恢复点的每个阶段可独立调用并单独断言前置条件与回滚效果；编排函数不再内联阶段内部判断。
- [ ] AC-008：`tests/unit/test_t075_supervisor_fonts.py` 的 mock 不再依赖 `# type: ignore[method-assign]`，断言语义不变，类型检查通过。
- [ ] AC-009：项目门禁与黑盒 E2E 全绿；5 个目标函数复测 `CC<15`（或本 task 增量 ≤0），实测值写入实施笔记。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试：AC-001/002/003/004 由既有单元、集成与 E2E 回归断言；AC-005/007 由新拆分单元的直接调用断言；AC-006 用字段覆盖测试对 `ProfileConfig.model_fields` 与投影键取差集；AC-008 由 `tsc`/类型门禁与测试通过验证；AC-009 由 `scripts/run_gates.sh` 与黑盒模式门禁，CC 用 AST 计数脚本复测并记录。

## 上下文区

- 关联 spec：docs/specs/profile_management.md
- 来源：p167（2026-11-24 核实：5 函数 CC 24/21/19/37/35 仍超阈值，`extract_directory_metadata` 已降至 14 剔除；根因为领域边界缺失而非 CC 指标本身）

### 有意不测

- 生产环境真实 Docker/Chrome 的启动与恢复演练由既有 E2E 套件覆盖，本 task 只验证重构前后行为一致，不重复新增部署级用例。
- 未点名且本 task 无分支增量的历史高 CC 函数（`create_profile`、`create_app`、`runner.start`）不在本次复测与重构范围。

### 测试策略

- 先锁定行为：运行既有 profile update、extension migration、supervisor core、restore point 测试套件作为基线。
- 拆分后逐一新增针对新单元的断言：写路径三类校验、启动阶段前置条件与回滚、恢复阶段与回滚、扩展分类规则表。
- `ProfileConfig` 字段覆盖测试保证 ORM 投影无遗漏。
- 门禁按 `docs/blueprint/testing.md`：`scripts/run_gates.sh` 与 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无

### 风险与回退

- 风险：跨 DB 事务、并发生命周期与数据恢复的深层重构可能改变幂等、回滚或错误时序；手工字段投影迁移若遗漏字段会静默丢配置。
- 回退：单实现 commit，失败时 `git revert`；不保留旧函数或兼容开关。

### 依赖与约束

- 对外行为、API 契约、DB schema、恢复点格式一律不变，破坏性仅作用于内部代码结构。
- 不新增依赖与配置；不触碰 spec 中的长期行为描述以外的文档。
- 5 个目标函数与一处测试 mock 为唯一改动面；`extract_directory_metadata` 明确排除。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：写路径显式更新计划、单一 config→ORM 投影与生命周期阶段化边界。
- `docs/blueprint/decisions/`：新增 ADR 记录「按领域边界重构而非按 CC 指标拆分」的决定与理由。
- `docs/specs/profile_management.md`、`docs/specs/runtime_lifecycle.md`、`docs/specs/storage_and_artifacts.md`：front matter `tasks` 登记 t107。
