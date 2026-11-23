---
tid: "t105"
slug: "proxy_probe_expiry_auto_reprobe"
title: "取消代理观测 TTL 并统一快照失效语义"
status: "done"
branch: "t105_proxy_probe_expiry_auto_reprobe"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "5715c0bddf5ae1097faf4ef0105f718cf23228f4"
spec_source_sha: "5715c0bddf5ae1097faf4ef0105f718cf23228f4"
depends_on: ""
conflicts_with: ""
note: "来源 p168；用户 2026-11-23 裁决取消 24h TTL：观测快照整条永久有效，仅端点/凭据变化时失效并重测；上一版'过期自动重测'方案作废"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 领域层删除 `OBSERVATION_TTL_SECONDS` 与 `expires_at`：`observation_is_current` 改为纯端点身份判定（三类状态统一，`ok` 另需出口 IP 与国家码），无时间参数。
- 仓储层：`_visible_observation` 统一按指纹/凭据版本判定；`_latest_observation_geo_subquery` 先按每代理最新行排序再筛 `ok` 且国家码非空，collection 与 countries 口径一致；写入不再带 `expires_at`。
- 服务层与契约：两处成功观测写入删除 `expires_at`；`ProxyResponse`、OpenAPI 两份 schema 与前端生成类型同批重新生成。
- 迁移 0018（`b2c3d4e5f601`，只进不退）删除 `proxy_egress_observations.expires_at`；同步更新依赖旧 head 常量的迁移测试。
- 测试：新增 `test_t105_observation_expiry_retirement.py` 迁移前后验证；改写 t052 领域/仓储、t076 collection、t095 历史断言为无 TTL 语义。
- 文档：spec §7 与 front matter、blueprint domain/architecture/testing、新 ADR 042（取消 TTL）同步；历史 ADR 029 不回写，替代关系由 042 记录。
- 门禁：`scripts/run_gates.sh` 全量通过（contract 388、unit 2451、integration 225、frontend 752、build 通过）。
- 黑盒：从主分支运行栈取 8 个不可变镜像 ID + 密封引擎/GeoIP 缓存后跑 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`。全量门禁（contract 388 / unit 2451 / integration 225 / frontend 752 / build）全绿；E2E 并行阶段 44 passed / 2 skipped / 0 failed。E2E serial 阶段在本机多栈并存（主栈 0084-0089 六个浏览器实例 + 多轮 E2E 并发）下出现资源竞争的偶发 F，日志被超时截断；单独重跑 3 个 fingerprint 用例 3 passed、6 个 runtime/cache 用例 6 passed，确认失败为环境争用而非代码缺陷。另以 worktree 代码起真实 API + 真实 SQLite 做 HTTP 黑盒：观测 `observed_at` 设为 4000 天前，`/proxies/collection` 与 `/countries` 仍返回 `ok/777ms/JP/Tokyo` 且无 `expires_at`，重建 API 进程（模拟重启）结果一致（`.scratch/blackbox_t105_api.py`）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-23T13:50:00+08:00)

派 full review（code + test reviewer），独立于实施侧复核 AC 打勾与交付内容。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t105_code_f001|minor|已修|`proxy_country_ranges` docstring 遗留已删除的 TTL 过期口径，改为描述最新行口径|repository.py:2372-2380|

Round 1 verdict：code PASS（1 minor）/ test PASS（clean）。f001 修正 docstring 后交付内容变化，进入 Round 2 重审。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足，待 review 后 finish
- 测试：全量 `scripts/run_gates.sh` 通过；contract 388、unit 2451、integration 225、design lint/check 通过、frontend 752 项通过、生产构建通过；新增迁移用例与改写后的 TTL 语义用例全部通过。
- 黑盒：主分支镜像 + 密封缓存下 E2E 并行阶段 44 passed / 0 failed；serial 阶段本机多栈资源争用致偶发失败，单独重跑 9 个用例全过；针对本 bug 的真实 HTTP 黑盒（含进程重启模拟）通过。
- review：Round 1 code PASS（1 minor f001）/ test PASS（clean）；f001（docstring 遗留 TTL 措辞）已修。Round 2 重审 code PASS / test PASS，0 新 finding，`review-status overall=PASS / review_scope=ok / ac_review=ok`。6/6 AC 全部 TICK-VALID re_verified。
- AC 判定：全部勾选，见 `task.md` 行内 `- [x]`。

### 结果摘要

- 实现已完成；全量项目门禁与针对性 HTTP 黑盒通过；E2E 全栈在本机多栈并存下有偶发资源争用，单独重跑通过，非 t105 缺陷。
- specs_index：`docs/specs/proxy_management.md` front matter `tasks` 已登记 t105。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
