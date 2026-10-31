# GEPA 五任务：正式实验前准备验收

已补齐离线运行交接包；**READY_TO_RUN=false，未启动真实实验**。
Solver 为 OpenLux GPT-4.1 Mini，Optimizer 为 Qwen3.7-Flash；原始数据划分、seed0、
原生 Pareto、关闭 Merge、作者评分和原生搜索阈值保持原设置。模型替换偏离仍明确披露。

## 本轮完成

- 修复 Baseline/Test 结果保存：作者 `Evaluate` 输出三元组，现从中正确提取 prediction。
  正确率和原评分器未变；此前保存代码可能在调用完成后失败。
- 新增只读 run-pack 预检：15份数据文件、2,852条记录、159份 NLP 文件、146项环境版本、
  Wikipedia 语料及配置/上游来源哈希核验通过。环境探针显式采用运行脚本的本地包路径，
  保留项目与固定 GEPA 的元数据版本；没有把路径缺失误报为安装版本变动。
- 隔离候选从已提交父版本建立，只加入本次 paper 准备文件；未混入主工作区的其他源码修改。
  已准备16份未激活的阶段模板及具体私有命令；源码 SHA、真实授权、部署/未来结果绑定仍待完成。
- 嵌套目录的演练发现 Windows 路径过长，保留失败证据并中止该布局的检查。
  改用短目录后，真实 runner 的假模型四阶段演练通过；拟定正式输出路径最长为200字符。

## 验证

主工作区当前测试：**413 passed**；隔离发布候选：**407 passed**；专项：**42 passed**。
两套测试均按既有规则排除18项历史用例、4个历史评分测试模块；未声称全部历史重放通过。
两套完整测试的数量差异来自隔离候选未包含其他尚未提交的部署修改及对应测试。
production compileall、预检、CLI 和四阶段落盘演练通过，所有验证进程及子进程网络尝试均为0。

四阶段演练：Canary → 原生 GEPA 搜索 → Baseline Test → Selected Test，
成功落盘预测、正确加载选择程序，检查角色、划分读取及前后校验。
使用合成数据、假模型及合成专用授权夹具；不等于真实模型成绩、真实 API 授权或已提交源码冻结。
沿用未改变实现的21例 Windows 评分/反馈对齐、2,852条数据存储对齐以及双模型重试/缓存证据，
明确区分本次重跑的检查与复用证据。

## 待满足的启动条件

1. 配置执行环境的 `OPENLUX_API_KEY`、`OPENLUX_BASE_URL`。现有 LWJ 变量存在，值未披露。
2. 用户明确授权本地提交隔离候选，随后冻结实际源码 SHA 并确认干净；本轮未提交或推送。
3. 对精确源码、部署、角色和安全上限另行授权双模型 Canary，并验证真实可用性。
4. HotpotQA/HoVer 所需全量 BM25 索引仍按用户决定延期；约2GB 可用内存未达到8GiB 门槛。
5. 对正式搜索与最终 Test 范围、提议的操作保护上限给予明确授权。其他三任务可独立满足适用条件。

原生搜索阈值总和21,193；Baseline 加 Selected Test 共2,340条逻辑评价。
阶段计划中的逻辑/物理/墙钟保护值是供审批的提案，尚未激活；触限应中止而非宣告完成。
本轮真实 API 调用、模型 tokens、已激活授权均为0。历史原始响应和成绩未修改。

详见[准备与交接说明](../../docs/gepa_paper_formal_preparation_v1.md)、
[主预检](../../experiments/preparations/gepa_paper_formal_preparation_20261031/preflight.json)、
[候选预检](../../experiments/preparations/gepa_paper_candidate_preparation_20261031/preflight.json)、
[阶段提案](../../experiments/preparations/gepa_paper_formal_preparation_20261031/phase_plan.proposed.json)、
[验收统计](summary.json)。
