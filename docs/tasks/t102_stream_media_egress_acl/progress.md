---
tid: "t102"
slug: "stream_media_egress_acl"
title: "恢复 Stream 回环媒体发布与网络级出口隔离"
status: "done"
branch: "t102_stream_media_egress_acl"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "190d652503cf5c2e9a6d14a91adc2f85d0df9547"
spec_source_sha: "190d652503cf5c2e9a6d14a91adc2f85d0df9547"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 版本化媒体网固定 Gateway 和 Stream 地址。在创建 Stream 之前，由带 `NET_ADMIN` 的一次性 Supervisor 辅助容器在 Docker daemon 的 Linux 网络命名空间原子安装桥级 ACL。媒体网替换或拆除后清理对应规则；回退到不认识该 ACL 的版本时由发布入口清理已撤销网桥的规则。
- 实际升级发现，旧 Browser Agent 被替换后，内核规则仍保留在原 Browser 的命名空间。新 Agent 在首次安装时只接管完全匹配的内核规则，既有冲突策略仍拒绝覆盖。
- 全量 E2E 暴露宿主 UDP 并行分区忽略自定义基址、旧恢复夹具仅在宿主运行 Gateway。测试分区继承指定基址，旧夹具通过受控网桥端点接收 Stream 信令。
- 首轮审阅后，Browser 规则验证保留链内顺序和重复项。Supervisor 在首次接管前重装运行中 Stream 的 ACL，无法安装时停掉受影响的 Stream。该流程在 Supervisor 启动时运行一次。
- SIGKILL 真机回归验证了 ACL 安装后的控制面接管。旧逻辑同时等待 Browser 与 Stream 的容器策略标记，现仅验证 Browser 标记，随后按媒体网契约收敛 Stream。Protocol schema 重新导出，字段和版本无变更。
- 全量 E2E 发现旧容器图用例仍要求 Stream 具备容器策略门禁。以新节点替换，保留原 Gateway、凭据和生命周期覆盖，增加媒体网拓扑、Stream 隔离与 Browser-only Agent 断言。新节点用最终镜像实测通过。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-21T20:24:09+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t102_code_f001|important|已修|逐链比较规则顺序和重复项，保持链间输出顺序独立|`src/backend/cbrowser/supervisor/network_policy.py`|
|t102_code_f002|important|已修|接管前重装配对媒体网 ACL，安装失败停止现有 Stream|`src/backend/cbrowser/supervisor/docker_adapter.py`|
|t102_code_f003|minor|已修|更新媒体网接管说明，去掉旧链路本地规则|`docs/specs/webrtc_remote_display.md`|
|t102_test_f001|important|已修|恢复夹具启动纳入清理范围，R3 保证清理步骤互不阻断|`tests/e2e/test_supervisor_recovery_e2e.py`|

### Round 2 (2026-11-21T20:35:26+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t102_code_f004|important|已修|重启接管只要求 Browser 策略标记，Stream 由网桥 ACL 保护|`src/backend/cbrowser/supervisor/core.py`|
|t102_code_f005|minor|已修|从模型重新导出 Policy Agent schema 的媒体隔离描述|`schemas/runtime/policy_agent_protocol.json`|
|t102_test_f002|important|已修|恢复路径采用 Browser 标记，真实重启验收加控制面 readiness|`src/backend/cbrowser/supervisor/core.py`|

### Round 3 (2026-11-21T20:44:58+08:00)

Round 3 零 finding。两轴逐条复核三个部署 AC。

### Round 4 (2026-11-22T00:54:51+08:00)

Round 4 零 finding。两轴复核容器图节点替换与两项实机复验。

### Round 5 (2026-11-22T00:59:20+08:00)

Round 5 零 finding。两轴复核历史探针的决定和后续任务补记。第四轮镜像、测试和三条验收证据继续有效。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：三条部署验收全部满足。
- 测试：统一门禁的契约、单元、集成、前端、构建、协议与镜像校验通过。Docker/Chrome E2E 原始运行 104 通过、2 失败、2 默认跳过。跨 IPC 探针原样复跑通过，容器图节点替换后复跑通过。按原始结果与复验共 106 通过、2 默认跳过。六项恢复与重试专项全部通过。原始门禁和两项复验分别保留于主仓 `.scratch/t102_evidence/verification_summary.md`。
- 黑盒：实际 OrbStack 和 Chrome 验证回环 UDP 视频、音频、键盘、Gateway 信令、完整拒绝矩阵和辅助镜像失败封闭。v0.2.1 → t102 → v0.2.1 验证两个 Profile、Agent 形状及回退 ACL 清理。删掉测试 ACL 并重启 Supervisor 后，旧容器保留、两个 Profile 的 readiness 恢复。证据见主仓 `.scratch/t102_evidence/acceptance/summary.md`。
- review：第五轮代码与测试轴均通过，全部既有 finding 已关闭，三条 AC 均判 TICK-VALID。见 [`review_code.md`](review_code.md) 和 [`review_test.md`](review_test.md)。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Stream 仅保留本 Profile Gateway 信令和回环媒体回复。验收未改动其它部署的 16 个运行容器。

### 长期文档闭环

- 在 `browser_isolation`、`webrtc_remote_display`、`release_deployment` 三份 active spec 中登记 t102，更新架构、原拓扑 ADR 和部署说明。
