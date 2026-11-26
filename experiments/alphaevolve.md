# AlphaEvolve 提案搜索实验

本实验面向维护提案搜索循环的工程师。运行 `python experiments/alphaevolve_demo.py` 可比较从错误求和表达式开始的四条搜索路径。每行 JSON 包含最终表达式、独立样本结果、评估次数、模拟提案次数、耗时和不同表达式数。目标取指定输入上估算运算次数之和的倒数。每轮最多评估三次，组合流程包含修复和种子复评。模拟提案只从三个固定表达式中取值。真实模型的提案质量和耗时仍需另测。实验入口沿用提案评估回调。MAP-Elites 的入格条件只影响搜索选择，生产发布仍由原有 judge 和 gate 决定。

## 实现对应关系

AlphaEvolve 论文描述模型修改代码、评估程序反馈并据此继续搜索。[论文](https://arxiv.org/abs/2506.13131)

对照源码取自 OpenEvolve 的 Apache-2.0 版本 `ada158763be59be29d3e46dbbb583bceed6b9cea`。下表的类名和默认值属于这个版本。[参考实现](https://github.com/algorithmicsuperintelligence/openevolve/tree/ada158763be59be29d3e46dbbb583bceed6b9cea)

| OpenEvolve | 本实验 |
|---|---|
| ProgramDatabase.add 与特征分箱 | ProposalEngine 保存候选及父编号。AlphaEvolvePolicy 从已评估候选重建每个格子的最优解。同分保留先入者。 |
| sample 返回父程序和参考程序，默认五个参考 | 每轮按随机种子和已选父代次数抽取一个格子，再从其他格子取至多两个参考。 |
| PopulationStrategy 提供准入、替换、淘汰和迁移钩子 | 使用现有 Policy。可选 select_parents 钩子向 reflect 动作加入 inspirations 编号。旧策略继续调用 choose。同步 proposer 接口只能接收父代，使用参考程序需消费动作接口。 |
| utils/code_utils.py 应用代码修改，evaluator.py 可分阶段评估 | 修改由调用方生成，沿用 ProposalLoop.apply 和外部评估。示例评估器只接受预设表达式，独立样本在最终选择之后评分。 |
| controller.run 接受迭代数和目标分数 | ProposalLoop 沿用评估次数、轮数、候选总量及 token 限制。token 限制根据已返回用量在动作之间检查。 |
| controller 保存检查点，database 保存种群和岛状态 | 保留 JSONL 提案记录和 ProposalLoop.to_dict 快照。在原归档上用 ProposalLoop.from_dict(state, policy=policy) 恢复，调用方提供相同策略配置。 |

## 配置与扩展

在现有 `experiment search` 命令中选择 `--policy alphaevolve`。场景 JSON 可添加以下字段。此命令对已有分数做选择。多代生成走示例中的 ProposalLoop。

```json
{"alphaevolve":{"objective":"objective","correctness":"correct","dimensions":{"size":[16,32]},"seed":0}}
```

评估器提供所有维度、目标和正确性分数。正确性为 1 的候选才能入格，目标越大越好。阈值处归入右侧格子。增加一个维度时同时修改评估器输出及 dimensions。空维度配置保留一个格子。

## 候选交接与适用范围

示例将修复器选出的 draft 交给新 ProposalEngine.add，接收方重新验证并评估。Agentless 提交 f848f6a7 的 run_trial 则产生带 base_rev 的 candidate.json 和独立的 result.json。只有 decision 为 pass 的修改才适合作为优化起点。在支持同一 region 的检出上，可把 candidate.json 放入草案的 candidate 字段，保留 target_kind，再通过现有修改应用和评估流程。该分支使用 tooling.ibmc_analyzer，当前主线没有登记这一修改范围。因此示例中的修复器采用确定性替身。GEPA 比较使用提案层 GepaPolicy。

本次实验不含岛迁移、评估级联、模型集成、进程崩溃时的跨文件事务，或针对真实 iBMC 修复的性能评测。恢复支持在已完成的动作边界保存的快照。

## 真实 iBMC 修复交接

运行 `python experiments/agentless_alphaevolve.py .`。所在 Git 仓库需包含 f848f6a7。示例在临时工作树内用该提交的 Agentless 入口和随仓回复执行修复，核对 result.json、基线提交、目标文件和被替换文本，再把完整的修复后源码作为提案种子。修改范围限定在分析脚本。评估程序和 7 个样本由固定提交提供。

本次运行从 4/7 提高到 7/7。种子 P-0001 和子代 P-0002 分别通过 7 项探测和 30 项回归检查。子代把每条被读取的非空行上的 strip 调用从两次减到一次。目标按这两个固定表达式对应的调用次数计算，实际端到端耗时收益尚未测量。参考候选、修复文本及测试均在本地处理。

## 结果解释

求和示例的三个独立输入全部通过。仅修复的估算成本为 61，三种优化路径均为 9。直接优化在第 1 次评估找到公式，修复后优化在第 3 次找到，其中第 2 次用于接收方重新评估种子。模拟提案器可以直接给出公式，所以该结果只说明本题在这一提案序列下没有热启动收益。真实 iBMC 示例验证两个分支可以通过修复后的源码交接，尚无同预算的真实模型对照。

论文第 2 节还描述岛模型、MAP-Elites 和可选的分阶段评估。OpenEvolve 的探索与利用比例、分箱配置及 PopulationStrategy 接口是公开实现的具体选择。[AlphaEvolve 方法](https://arxiv.org/html/2506.13131v1)
