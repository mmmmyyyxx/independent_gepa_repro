# GEPA 五任务准备：Qwen3.7-Flash 优化模型修订

用户要求将反思与 Prompt 改写模型设为 Qwen3.7-Flash。此次只修订新的五任务准备，
不修改其他研究的模型配置、历史数据、响应或成绩。模型 API 调用与真实 tokens 均为0；
未提交、未推送，`READY_TO_RUN=false`。

| 角色 | 模型 | 接口配置 |
|---|---|---|
| Solver | `gpt-4.1-mini-2025-04-14` | OpenLux，沿用原五任务准备 |
| 反思 / Prompt optimizer | `qwen3.7-flash` | LWJ，沿用仓库已有环境变量名称 |

两者仍采用 temperature1.0、max_tokens16384，无模型 fallback。
本轮没有验证供应商是否提供确切模型；需单独授权的 Canary。
Qwen 使用未注明快照的别名，不能证明后端权重固定或与论文模型等同。

原始数据成员、seed0、每任务一次、五个原程序及评分、原生 Pareto、关闭 Merge、
各任务搜索阈值和重试政策均保留。反思模型替换是明确的模型条件偏离，因此应报告为
采用替代优化模型的 GEPA 方法复现，不能称为论文相同模型条件的成绩复现。
作者代码默认 `teacher_lm=None` 并复用配置的任务 LM；Qwen3-8B 是另一套既有部署，
不由本协议实例化。

## 实现与身份

原始程序的所有预测器显式绑定 Solver LM；全局 DSPy LM 绑定 Qwen 反思 LM。
作者原生反思表达式会读取全局 LM；候选 deepcopy 保留 Solver 绑定。
不进入作者非空 teacher_lm 分支（该分支引用不存在的成员），不修改作者源码或模板。
两个真实模型标识分别进入原始 DSPy 缓存键。

配置、manifest 和授权模板已采用新 V2 身份；旧 V1 授权不可接受。
授权、Canary、缓存、最终候选来源及运行回执均绑定两个模型和两组部署哈希。
Baseline/Test 仅实例化 Solver；物理边界校验角色、模型、部署和解码参数，按角色统计 tokens。
密钥仅在物理边界读取，不进入保存的 Prompt 程序。

主要改动为 `paper_suite/contract.py`、`runtime.py`，新增 `models.py`，
并扩展 `offline.py`、两份专项测试及独立 V2 配置、协议文件、文档。
旧 V1 准备文件和报告完整保留。

## 离线验收

当前测试集 **408 passed，18 deselected**；另有4个历史评分测试模块按既有规则不收集。
专项37项通过。编译、六个 CLI help 通过；未授权启动被拒绝且未消费任何 scope。
原始 GEPA 双模型模拟产生2个候选，原生/独立逻辑计数均14，模拟物理请求16，
其中1次暂时性超时成功重试、1次反思调用。401在1次尝试后中止，不产生错误评分。
检查实际模型/接口/密钥路由、两模型缓存键分离、同一反思精确命中缓存、
最终程序序列化后 Solver 绑定保留且不含密钥。五个原始程序的 Solver 阶段均未调用反思 LM。

复用前次21例 Windows 评分与反馈对齐和2,852条数据存储对齐证据：
相应实现、上游源码、数据、环境锁和资源未变，本轮未声称重新执行这些未受影响的检查。
全量 BM25 索引按用户决定仍延期；正式运行另需源码冻结、双模型 Canary 及精确授权。

查看[修订协议](../../docs/gepa_paper_five_task_reproduction_qwen37_v2.md)、
[manifest](../../experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_windows_v2/manifest.json)、
[readiness](../../experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_windows_v2/readiness.json)及[验收统计](summary.json)。
