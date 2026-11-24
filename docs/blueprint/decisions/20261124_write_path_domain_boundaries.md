# ADR 044：按领域边界重构写路径与生命周期，不按圈复杂度指标拆分

- 日期：2026-11-24
- 状态：accepted
- 关联：t107 / p167

## 背景

p167 源自 t104 review minor，字面目标是拆分 6 个 `CC>=15` 后端函数。复测当前 main：5 个函数仍超阈值（`ProfileService.update_profile` 24、`ProfileRepository.update_profile` 21、`_match_legacy_entry` 19、`SupervisorCore.start_profile` 37、`restore_point` 35），`manifest.extract_directory_metadata` 已降至 14。高 CC 是症状：写路径策略、数据形状映射、生命周期状态机与身份分类规则都写在长函数里，新能力只能继续增加分支。

## 决策

1. Profile 更新提升为显式更新计划：补丁归一化、平台/字体绑定、引用校验、扩展校验、错误翻译各自独立；编排方法只推进阶段。
2. `ProfileConfig.model_fields` 是 config→ORM 投影的唯一字段来源，删除手工 22 字段读写清单；新增配置字段不再需要改第二处。
3. Supervisor 启动与恢复点切换改为阶段化状态机，每个阶段独立承载前置条件、副作用与回滚，编排函数只推进 phase。
4. 扩展身份匹配改为纯分类规则表，结论文案与分类解耦。
5. 不保留兼容 wrapper、feature flag 或双轨判定；旧胖函数直接删除，`extract_directory_metadata` 明确排除。

## 理由

按指标拆分只产生更多 helper，决策分叉仍在；把领域决策提升为可独立调用的边界后，新需求有明确落点，漏分支与状态漂移从结构上减少。单一字段投影消除与模型平行的第二份契约，符合零兼容性负担。

## 后果

- 跨 DB 事务、并发生命周期与数据恢复的深层重构，由既有测试、新边界单测、全量门禁与真实 E2E 共同锁定行为不变。
- 对外 API、DB schema、恢复点格式与错误语义不变；内部函数签名破坏性调整，无兼容层。
- 实测 CC：五个目标函数分别降至 12、11、12、7、4。
