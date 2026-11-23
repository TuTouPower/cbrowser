# ADR 043：配置待应用事实进入读模型，视图层零版本比较

- 日期：2026-11-23
- 状态：accepted
- 关联：t106 / p170

## 背景

配置版本抬升后，运行实例仍绑定旧版本，界面需提示「配置变更待应用 / 应用并重启」。原实现把判定表达式 `runtime.config_version !== profile.current_config_version` 写在三个工作台组件内；环境管理列表与工作台入口页读取同一集合行却不比较，导致配置变更后列表仍显示「运行中」，用户必须进入工作台才看到提示。t098 统一了运行投影的数据，但没有统一语义。

## 决策

1. `config_pending` 是领域派生事实，谓词只在领域层定义一次：runtime 存在、`observed_state != "stopped"` 且 `current_config_version > runtime.config_version` 时为真；终态 error 仍为真以便用新版本恢复，停止态与无 runtime 为假。
2. 该事实随 `ProfileRuntimeProjection`（collection 行）、`ProfileRuntimeResponse` 与 `ProfileRuntimeStatusEvent`（SSE）三个读模型交付；不新增存储列，不改变版本抬升规则或 SSE 信封。
3. 前端任何界面只读 `config_pending`，删除全部版本比较式；待应用呈现收敛到单一 `ConfigPendingNotice`，「应用并重启」收敛到单一 `useApplyConfigRestart` 命令（stop + 以新版本启动 + 按 Profile 隔离 pending/error）。
4. 契约破坏性更新：OpenAPI 两个文件与生成类型同批替换，不保留兼容字段、双轨判定或 feature flag。

## 理由

派生事实位于读模型时，新界面天然获得该事实，漏判从「可能发生」变为「结构上不可能」；共享 helper 只是约定，无法根除同类缺陷。单一命令边界使 profile 作用域守卫不再依赖各组件自觉，消除规格中的约束补丁。

## 后果

- 后端新增三个只读字段并重新导出契约；所有构造 runtime 读模型的测试夹具需同步。
- 旧前端与新后端错配时按严格契约失败，不做兼容降级。
- 终态 error 的待应用语义与停止态不同，需在谓词单测真值表中锁定。
