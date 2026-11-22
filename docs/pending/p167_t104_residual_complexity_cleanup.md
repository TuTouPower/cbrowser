---
pid: "p167"
slug: "t104_residual_complexity_cleanup"
status: "todo"
---
# p167 拆分 t104 Review 遗留高圈复杂度后端函数

- 来源：t104 遗留（Round 2 Code Review 非阻断 minor `t104_code_f012`、残余 `t104_code_f011` 与 Test Review 观察项）
- 内容：在不改变对外行为与契约的前提下，将以下高圈复杂度（`CC >= 15`）后端函数及跨文件历史测试重构为职责单一的小型 helper：1）`src/backend/cbrowser/services/profile_service.py` `update_profile`；2）`src/backend/cbrowser/adapters/database/repository.py` `update_profile`；3）`src/backend/cbrowser/extensions/manifest.py` `extract_directory_metadata`；4）`src/backend/cbrowser/adapters/database/extension_paths_migration.py` `_match_legacy_entry`、`src/backend/cbrowser/supervisor/core.py` `start_profile`、`scripts/restore_point.py` `restore_point`；5）顺带清理历史 `tests/unit/test_t075_supervisor_fonts.py` 对 `report_terminal_observation` 的 `# type: ignore[method-assign]` mock 写法。因以上均属 Round 2 `minor` 维护性建议且非当前功能阻塞，为避免扩大收尾 diff 并保持 Round 2 `reviewed_scope` PASS 稳定性延后至独立重构 task 办理。
- 处理：未开
