# GEPA 五数据集忠实复现：离线准备报告

2026-10-31。已完成协议核对、数据成员冻结、Windows 适配和离线运行保护。
按照用户决定，全量 BM25 索引延期至机器空闲后构建。
**未启动模型实验；READY_TO_RUN=false；模型 API 调用及真实模型 tokens 均为0。**

## 采用的实验定义

以[论文 v2](https://arxiv.org/html/2507.19457v2)及
[作者复现源码](https://github.com/gepa-ai/gepa-artifact/tree/cbefbc1aa0f43dd39874ec4bf42211365dbda42e)
为依据，执行原始 `gepa_artifact.gepa.gepa.GEPA`，保留原生实例 Pareto 选择，关闭 Merge。
原有 matched-team、单 Prompt MATH、C-EVOLVE/Hendrycks 评分和历史成绩均不变。
这次使用各 benchmark 的作者评分函数，不将它们接入旧 MATH 评分路径。

作者脚本 `SEEDS=[0]`，故每个任务一次 seed0 搜索，不沿用先前三次 seed42。
作者没有单独传入 Teacher，反思默认复用任务 LM；此次两种角色均请求 OpenLux
`gpt-4.1-mini-2025-04-14`，temperature1.0、max_tokens16384。
确切模型标识的可用性尚待另行授权的 Canary 验证；不自动退回其他模型或供应商。

| 数据集 | Train | Validation | Test 行数 | 原生搜索预算阈值 | 原评分 |
|---|---:|---:|---:|---:|---|
| HotpotQA | 150 | 300 | 300 | 6,871 | DSPy 答案 exact match |
| IFBench | 150 | 300 | 294 | 3,593 | 宽松检查后，满足约束的比例 |
| HoVer | 150 | 300 | 300 | 7,051 | 检索到全部 gold 文档标题 |
| AIME-2025 | 45 | 45 | 150 | 1,839 | answer 字段转整数后相等 |
| LiveBench-Math | 121 | 121 | 126 | 1,839 | 作者按题目子任务分派的评分函数 |

原生搜索阈值合计21,193。它们不是严格物理请求数或 token 上限：原版在迭代边界检查，
完整迭代可能越过阈值，部分跳过路径也不增加原生计数。因此同时保留独立任务尝试、
物理调用、重试、缓存及角色 token 账本，不将原生计数误报为精确等计算量。

## 数据及忠实性边界

- 固定作者源码、DSPy `gepa_study`、上游数据 revision、文件哈希及有序成员哈希。
  LiveBench 使用368题历史快照，按照原代码0.33/0.66切分得到121/121/126。
- HoVer 按原 loader 选三文档样本。Train/Validation 有1条相同 claim；用户明确选择
  保留并披露。Test 与两者均无内容重合。HF ClassLabel 的整数编码按原 schema 保留。
- AIME Test 为30道题各重复五遍；保留原 DSPy 缓存，不能将150行解释成150次独立生成。
- HotpotQA、HoVer 各四个预测模块，IFBench 两个模块，两项数学任务各一个 CoT 模块。
  使用原初始指令、程序流程、反馈和最终 Validation 选择；不改成三个 Prompt 块或投票团队。
- OpenLux 替代论文的直接 OpenAI 部署；原始历史依赖没有完整锁，现有 Windows 环境是
  经验证的重建版本。未导入原 MIPRO 预热缓存。这些差异均须随正式结果披露，不能保证复得论文分数。

## 离线验证

| 检查 | 结果 |
|---|---|
| 作者两份 Git 源码及既有 vendor | 固定提交、干净；源码未修改 |
| 数据存储适配 | 2,852条分割后样本，payload 一致；原 IFBench loader 独立核对 |
| Windows 数学评分 | 21组合成输入，分数及反馈文本与原评分函数一致 |
| 五套原始程序 | 模拟完整流程通过；加入计数器前后输出及检索阶段一致 |
| 子进程控制 | 超时、崩溃、回收、后续请求、大结果 IPC 通过 |
| 原版 GEPA 联调 | 两个候选，一次反思；原生计数与独立计数均14 |
| 原版 GEPA 重试联调 | 首次模拟超时后恢复；16次模拟物理分派，含1次失败，成功输出不变 |
| 原版 GEPA 致命故障联调 | 模拟401仅尝试一次，立即中止，未输出错误评分 |
| 完整当前 pytest | 397 passed，18条历史案例 deselected；4个历史模块按既有分类不收集 |
| 最终增量 pytest | 28 passed；与完整检查的用例并集覆盖399个当前用例 |
| compileall、6个 CLI help、依赖检查 | 通过 |
| 无授权启动检查 | 拒绝，未构建真实调用、未消耗授权 scope |

397项完整检查与末次28项检查是两份证据，未把增量检查说成另一次完整检查。
原评分源码的3条转义符弃用提示仍保留。未声称所有历史回放均已执行。
验证进程及其子进程在预导入网络封锁下运行，观测到的网络尝试为0。
资源/依赖的公开下载另行记录，不属于模型调用。

Windows 适配保持原正常评分函数，替换不可 pickle 的进程传输；仍保留8秒数学比较
期限。Windows spawn 启动耗时也计入期限，故不声称与 Linux 的超时边界完全相同。
没有结果的异常死进程按运维故障中止，不伪造答错。普通数学异常仍遵循作者处理。

## 运维适配及正式启动条件

新增阶段 runner 包含独立逻辑/物理/角色 token 账本，先保存响应再评分，有限瞬时故障
重试，非瞬时错误中止，独立运维上限，精确来源检查与一次性授权。逻辑名额在根程序
执行前预留，嵌套模块不重复计数；不改变 Pareto、候选接受或最终获胜者选择。
失败请求的未知用量显式保留，不伪造为零。Baseline/Search/Test 的访问和模型角色分别绑定。

目前缺少的是**正式执行条件**：

1. 用户同意延期的全量 BM25 索引及其完成凭据。
2. 本次源码的本地提交、干净执行副本和最终来源冻结。
3. 精确 Canary 授权及 OpenLux 日期版本可用性验证；随后另行冻结搜索/Test 阶段授权。

授权模板默认为 false，未设置可执行凭据。此前 GEPA、A2 Test 或其他实验授权不能复用。
本轮没有提交、暂存或推送，没有启动或改变其他正在运行的实验。

## 交付位置

- [完整协议与离线命令](../../docs/gepa_paper_five_task_reproduction_v1.md)
- [配置](../../configs/gepa_paper_five_tasks_openlux_windows_v1.json)
- [Manifest、数据/源码/环境清单及授权模板](../../experiments/protocols/gepa_paper_five_tasks_openlux_windows_v1/manifest.json)
- [Readiness](../../experiments/protocols/gepa_paper_five_tasks_openlux_windows_v1/readiness.json)
- [机器可读摘要](summary.json)

实现集中在 `src/independent_gepa/paper_suite/`；准备和受保护运行命令位于
`scripts/*gepa_paper*.py`。独立 Windows 依赖锁位于
`requirements/paper-suite-windows.lock.txt`，专项测试为
`tests/test_gepa_paper_preparation.py`、`tests/test_gepa_paper_control.py`。
原始数据、模型指令、模拟原始输出、响应体、缓存和详细日志均留在 ignored runs。

结论：本轮离线准备范围完成，包含用户接受的索引延期；下一阶段为 **HOLD**，不得直接启动正式实验。
