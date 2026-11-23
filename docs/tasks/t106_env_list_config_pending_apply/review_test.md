# Task review t106（reviewer_focus: 测试）

- task：`t106_env_list_config_pending_apply`
- spec：`docs/tasks/t106_env_list_config_pending_apply/task.md`
- diff_anchor：`9940cd79c2020bdeff43a5a453df9203356a7b85`
- target：`git diff 9940cd79c2020bdeff43a5a453df9203356a7b85`
- round：1
- reviewed_at：2026-11-24T00:50:11+08:00

reviewed_scope: 13be7a1d370e8251

## Findings

### t106_test_f001 - SSE 读模型 config_pending 填充仅有「设值即断言」恒真断言，生产填充路径零覆盖

- 严重度：important
- 锚点：AC-002（`config_pending` 随 `ProfileRuntimeStatusEvent`（SSE data）交付，由 SSE 初始快照与实时发布填入）；连带削弱 AC-008 的 SSE 来源可信度。
- 位置：`tests/unit/test_t106_config_pending.py:63-71`（`test_sse_event_carries_the_same_fact`）
- 问题：该用例先在构造器写入 `config_pending=True`（第 69 行），再 `assert event.config_pending is True`（第 71 行）；断言由构造输入直接决定，恒真，不触达任何生产填充逻辑。生产填充位于 `src/backend/cbrowser/api/v1/router.py:230`（初始快照 `subscribe_runtime_events`）与 `src/backend/cbrowser/api/runtime_coordinator.py:1107`（实时发布 `publish_profile_change`）。全仓 grep 确认：除本用例外，测试中 `config_pending` 的出现全是 `config_pending: false` 夹具，无一处调用这两个生产路径后断言其 `config_pending`。因此快照/实时发布填充若出错（如误用 `rt.config_version`、漏字段、停止态误报），AC-002 的 SSE 部分仍显示「已覆盖」，属假绿。次要影响：`EnvironmentListPage.test.tsx:1396-1418` 的 AC-008 用例直接 `queryClient.setQueryData` 注入集合缓存，绕过 `src/frontend/src/features/profiles/useProfilesQuery.ts:817/843/1177` 的 SSE→缓存字段合并，未验证事件字段真实流动（该缺口不单独阻断，因测试策略允许 cache 注入且「有意不测」排除真实端到端 SSE）。
- 建议：把 `test_sse_event_carries_the_same_fact` 改为驱动生产路径（`subscribe_runtime_events` 的 initial snapshot provider / `publish_profile_change`）后断言事件的 `config_pending` 随 `current_config_version` 与 `observed_state` 变化，至少覆盖错配为真、版本相等与停止态为假，使断言由生产逻辑而非构造输入决定。

## 结论

- 前轮 finding 复核：无（Round 1）
- 改测方向复核：`SessionHeader.test.tsx:357-485` 把 4 处用例标题与夹具从「版本比较」迁到读 `config_pending`，断言本体未变，属随 AC-007 的合法语义迁移，非迁就实现；无其它改测。
- 本轮新发现：1 条
- 未进表的提示：
    - `tests/unit/test_t106_config_pending.py:26` 新增 `# type: ignore[arg-type]`，位于参数化 helper 的 `observed_state=observed`，仅规避静态类型（str→ObservedState）；Pydantic 运行时仍校验枚举值，未降低行为覆盖，按「调查后判定、非语法命中」不报 finding。
    - `src/frontend/src/features/browser-session/SessionPage.test.tsx:229` 夹具用 `config_pending: configVersion > 1` 复刻谓词；谓词本身已由领域单测真实覆盖，此处仅作夹具数据，不构成冒充覆盖。
    - 行内应用用例（`EnvironmentListPage.test.tsx:1357-1394`）只断言 `stop` 调用与提示消失，未断言 `setDesiredState`（以新版本运行）；停止后 `config_pending` 即为假，提示消失可被 stop 单独满足。属「可再加 case」级 minor，不阻断。
    - 未跟踪交付 `docs/blueprint/decisions/20261123_config_pending_read_model.md` 未 `git add -N`，不出现在 `git diff`；但当前 scope 指纹与注入值一致（`13be7a1d370e8251`），确认派审后无改动，且该文件为纯文档、不属测试覆盖缺口。
- 总体判断：AC-002 的 SSE 读模型交付仅由恒真断言支撑、生产快照/发布填充零测试验证，阻断 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t106_config_pending.py:23-45` 真值表 7 例覆盖 starting/running/stopping/error 为真、stopped/版本相等/运行版本更高为假，加无 runtime 用例；独立复跑该文件 12 passed。
- AC-002：TICK-VOID，trust_prior。契约部分 `npm run check:api` 独立复跑退出 0、projection/response 有真实断言，但 SSE 读模型（AC-002 要求的第三模型）填充的唯一断言是恒真断言（`tests/unit/test_t106_config_pending.py:63-71`），生产快照/发布填充（`router.py:230`、`runtime_coordinator.py:1107`）无任何测试触达，打勾缺乏有效验证支撑。
- AC-003：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1357-1372` 断言 p1（pending=true）显示提示、p2（false）不显示；vitest 复跑该 surface 通过。
- AC-004：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1377-1386` 切卡片布局后同一字段经同一 `ConfigPendingNotice` 显示，p2 不显示，无口径漂移。
- AC-005：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1374-1394` 用 `fireEvent.click` 真实点击，断言仅 p1 触发 stop、其它行不受影响、目标行提示消失。
- AC-006：TICK-VALID，re_verified。`SessionEntryPage.test.tsx:345-359` 同屏断言待应用提示、应用入口与 `href=/session/p1` 共存；vitest 复跑通过。
- AC-007：TICK-VALID，re_verified。`SessionHeader.test.tsx:357-485` 迁到 `config_pending` 后断言三态口径；`SessionDetailsPanel.test.tsx`、`SharedProfileBanners.tsx` 改读该字段；全仓 grep 生产代码无「待应用 = 版本比较」残留。
- AC-008：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1396-1418` 向集合缓存注入 `config_pending=true` 后无需导航即出现提示，断言用户可观察行为；SSE 事件→缓存字段合并未直接断言，属次要覆盖扩展（测试策略允许 cache 注入）。
- AC-009：TICK-VALID，re_verified。领域单测 12 例、`npm run check:api`、3 个 surface 测试文件 62 例均独立复跑通过；全量门禁证据由实施侧 `scripts/run_gates.sh` 提供。

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-24T01:47:07+08:00)

reviewed_scope: be2e91f74e8fba39

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：`t106_test_f001` 已消除（真实修复，非撤回）。依据相对 `9940cd...` 的完整交付 diff：
    - 旧恒真断言用例 `test_sse_event_carries_the_same_fact`（构造时写 `config_pending=True` 再断言 `True`）已删除。
    - 新增生产共享工厂 `make_runtime_event_data`（`src/backend/cbrowser/api/v1/runtime_views.py:105`），其中 `config_pending=config_pending(current_config_version, rt)` 由领域谓词派生，非构造输入。
    - 两条 SSE 填充路径均改走该工厂：初始快照 `subscribe_runtime_events`（`src/backend/cbrowser/api/v1/router.py:224`，传 `p.current_config_version`）、实时发布 `publish_profile_change`（`src/backend/cbrowser/api/runtime_coordinator.py:1101`，传 `profile.current_config_version`）。
    - 新测试 `test_sse_event_factory_derives_config_pending`（`tests/unit/test_t106_config_pending.py:71`）直接驱动该生产工厂，3 例真值表（running 1/2→True、running 2/2→False、stopped 1/2→False）断言 `event.config_pending`，断言由生产逻辑而非构造输入决定。finding 列举的三种失败场景均可被捕获：误用 `rt.config_version`（第 1 例由 True 变 False 而失败）、漏字段（构造即缺字段）、停止态误报（第 3 例失败）。
    - 另新增 `test_collection_row_flips_pending_after_config_bump`（`tests/unit/test_t106_config_pending.py:96`）经真实 `ProfileRepository`/`ProfileService.list_profiles_page` 断言配置抬升前后集合行 `config_pending` 由 False→True，强化 AC-002 collection 行覆盖。
    - 独立复跑：`tests/unit/test_t106_config_pending.py` 14 passed；连同相关单测共 65 passed。
- 改测方向复核：本轮把旧恒真断言用例替换为驱动生产工厂的真值表用例，方向是「让断言由生产逻辑决定」而非「让断言迁就当前实现」；工厂为统一两条 SSE 填充路径的合法重构，非测试驱动实现。无迁就实现的改测。
- 本轮新发现：0 条。
- 未进表的提示：
    - 工厂测试未直接驱动 `subscribe_runtime_events` / `publish_profile_change` 两个 caller 校验其传入工厂的 `current_config_version` 来源；但 diff 显示两处分别传 `p.current_config_version` / `profile.current_config_version`，且 finding 列举的三种失败场景已在工厂层被捕获，属「可再加 case」级 minor，不阻断。
    - `tests/unit/test_t106_config_pending.py:82` 将 `import pytest_asyncio` 等导入置于文件中段，风格问题，不进 finding。
- 总体判断：`t106_test_f001` 已真实消除，SSE 读模型 `config_pending` 填充由生产工厂真值表有效验证，无未解决 critical / important，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t106_config_pending.py:23-47` 真值表 7 例驱动领域谓词（starting/running/stopping/error 为真、stopped/版本相等/运行版本更高为假），加无 runtime 用例，独立复跑通过。
- AC-002：TICK-VALID，re_verified。三个读模型均有真实生产断言：`ProfileRuntimeProjection.from_runtime`（:50）、`make_runtime_response`（:57）、`make_runtime_event_data`（:71）工厂真值表；`test_collection_row_flips_pending_after_config_bump`（:96）经真实 DB 断言集合行翻转；`npm run check:api` 本轮独立复跑退出 0，`d.ts`/OpenAPI 均含 `config_pending`；无存储列。前轮恒真断言已消除。
- AC-003：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1357-1372` 断言 pending=true 行显示待应用、false 行不显示。
- AC-004：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1377-1386` 卡片布局同字段经同一呈现单元显示，无口径漂移。
- AC-005：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1374-1394` `fireEvent.click` 仅目标行触发 stop、其它行不受影响、目标行提示消失。
- AC-006：TICK-VALID，re_verified。`SessionEntryPage.test.tsx:345-359` 同屏断言待应用提示、应用入口与 `/session/p1` 链接共存。
- AC-007：TICK-VALID，re_verified。`SessionHeader.test.tsx:357-485` 迁到 `config_pending` 后断言三态口径；`SessionDetailsPanel` / `SharedProfileBanners` 改读该字段；全仓 grep 无「待应用 = 版本比较」残留。
- AC-008：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:1396-1418` 集合缓存注入 `config_pending=true` 后无需导航即显示提示，断言用户可观察行为；SSE 字段合并属测试策略允许、且「有意不测」排除真实端到端时序。
- AC-009：TICK-VALID，re_verified。`tests/unit/test_t106_config_pending.py` 14 passed、`check:api` 退出 0、相关单测 65 passed 均本轮独立复跑；全量门禁证据由实施侧提供。

coverage = 9 / 9

verdict: PASS

## Round 3 (2026-11-24T01:58:02+08:00)

reviewed_scope: 1e2158725670a39d

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：`t106_test_f001` 仍为已消除（Round 2 真实修复，本轮在当前 scope 复核未回退）。SSE 读模型填充仍由生产共享工厂 `make_runtime_event_data`（`src/backend/cbrowser/api/v1/runtime_views.py:105`）以领域谓词 `config_pending(current_config_version, rt)`（:122）派生，非构造输入；两条调用路径仍传 profile 当前版本（`src/backend/cbrowser/api/v1/router.py:224-226`、`src/backend/cbrowser/api/runtime_coordinator.py:1101-1103`）；工厂真值表 `test_sse_event_factory_derives_config_pending`（`tests/unit/test_t106_config_pending.py:65-79`）与集合行翻转用例（:101-120）仍在且断言由生产逻辑决定，旧恒真断言用例未回归。
- 改测方向复核：本轮无测试改动；Round 2 的「恒真断言 → 生产工厂真值表」替换方向合规，无迁就实现的改测。
- 本轮新发现：0 条。
- 变更核实：相对 Round 2 指纹 `be2e91f74e8fba39`，当前 scope 指纹为 `1e2158725670a39d`。独立核实分歧仅在交付 Markdown（`.repo_template/scripts/md_format.py` 经 md_kx 只格式化 `.md`，影响 `docs/blueprint/*.md`、`docs/specs/profile_management.md` 的 blob，review/progress/prompt 等流程文件本就排除在指纹外），未触及源码与测试语义：领域谓词（`src/backend/cbrowser/domain/models.py:423-430`）、SSE 工厂及两条填充路径、四个关键测试文件的断言行与 Round 2 复核内容一致；新增/改动测试行中唯一的 `type: ignore` 仍是 `tests/unit/test_t106_config_pending.py:22` 的静态类型豁免（Pydantic 运行时校验枚举，未降低行为覆盖）。危险模式扫描未命中。
- 未进表的提示：无。
- 总体判断：以当前交付内容为准，前轮 blocker 已消除且未回退，全部 AC 的测试/验证证据本轮独立复验通过，无未解决 critical / important，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。领域谓词 `config_pending`（`src/backend/cbrowser/domain/models.py:423-430`）为 `runtime 存在 && observed_state != "stopped" && current_config_version > runtime.config_version`；真值表 `tests/unit/test_t106_config_pending.py:28-47` 7 例加无 runtime（:46-47）覆盖全部边界；本轮独立复跑 14 passed。
- AC-002：TICK-VALID，re_verified。三个读模型均由同一谓词派生（projection `src/backend/cbrowser/domain/models.py:1043`、response `src/backend/cbrowser/api/v1/runtime_views.py:83`、SSE event `src/backend/cbrowser/api/v1/runtime_views.py:122`）；工厂真值表（test :65-79）与真实 DB 集合行翻转（test :101-120）有效；本轮 `npm run check:api` 退出 0、生成 `d.ts` 含 `config_pending`；无存储列。
- AC-003：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1357-1383` 断言 p1（pending=true）显示待应用提示、p2（false）不显示。
- AC-004：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1385-1394` 切卡片布局后同字段经同一呈现单元显示，p2 不显示，无口径漂移。
- AC-005：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1366-1382` `fireEvent.click` 真实点击应用，仅 p1 触发一次 stop、其它行不受影响、目标行提示消失。
- AC-006：TICK-VALID，re_verified。`src/frontend/src/features/browser-session/SessionEntryPage.test.tsx:345-359` 同屏断言待应用提示、应用入口与 `/session/p1` 链接共存。
- AC-007：TICK-VALID，re_verified。`src/frontend/src/features/browser-session/SessionHeader.test.tsx:357-485` 三态口径断言；`SessionDetailsPanel` / `SharedProfileBanners` 改读该字段；全仓 grep 生产代码无「待应用 = 版本比较」残留。
- AC-008：TICK-VALID，re_verified。`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1396-1435` 集合缓存注入 `config_pending=true` 后无需导航即显示提示，断言用户可观察行为；真实端到端 SSE 时序属「有意不测」。
- AC-009：TICK-VALID，re_verified。本轮独立复跑 `tests/unit/test_t106_config_pending.py` 14 passed、`npm run check:api` 退出 0、3 个 surface 测试文件 62 passed、`npm run test:types` / `design:lint` / `design:check` 均通过；全量门禁证据由实施侧提供。

coverage = 9 / 9

verdict: PASS
