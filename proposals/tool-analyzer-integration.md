# 外部分析 skill 迁入方案

状态：提议

## 1. 结论

能迁；只迁已有材料的离线分析，现场操作交工程师。
先迁 ibmc_analyzer、prof-compare、cluster-analysis、cluster-compare。
选 C：自动与手动入口共用契约和验证门禁。
步骤 1 识别材料，步骤 5 调分析器；不扩 triage 维度。
本次只出方案；依据见下表，运行效果未验证。

本文供迁移实施者与评审者使用，回答改动范围、调用责任和批次条件。日常诊断无需读本文。章节顺序采用任务指定格式，优先于 doc-standards 的通用提案骨架。

引用约定：`上游/` 指仓库外克隆的 hu669293657/skills（固定提交 `6519f6f73ba68c6eaf51d9374644e4b60c84be0c`）；其余路径相对本仓检出根。

仓库基线为 `57f02ecc5adcf790a962e8ef0b80c9af6100f5cf`。上游来源为 [hu669293657/skills 固定提交](https://github.com/hu669293657/skills/tree/6519f6f73ba68c6eaf51d9374644e4b60c84be0c)。下文「拟」和「建议」均为本方案设计，不代表已有实现。

约束依据：验证先于交付、可观测、资源预算与诚实退化，见 `docs/spec/design-principles.md:31`、`:115`、`:127`、`:139`；仅建议、不访问客户环境，见 `CLAUDE.md:115` 起的 Key constraints。

首次检查已确认目标被 gitignore 忽略；实际落点由 `python scripts/shared_dir.py proposals-sessions` 解析。

## 2. 四段拆解表

「删」指删除迁入执行路径；「降级为给工程师的命令」指保留说明但 agent 不执行；「保留」仍须经过本方案的输出隔离与证据校验。

| skill | 输入契约 | 采集及现场动作 | 判读 | 交付 |
|---|---|---|---|---|
| ascend-dump-analyzer | 保留：一份或多份 dump、JSON/日志/目录；先辨实际格式。上游/ascend-dump-analyzer/SKILL.md:3、:14 | 降级为给工程师的命令：复制采集器到目标 Linux 机并采集进程视图。删 agent 复制和运行。上游/ascend-dump-analyzer/SKILL.md:24、:31 | 保留：覆盖状态、同角色配置差异、离线版本检查；差异不等于根因。上游/ascend-dump-analyzer/SKILL.md:15、:44 | 保留 HTML、Markdown；增加统一结果 JSON，不宣称上游已有此统一格式。上游/ascend-dump-analyzer/SKILL.md:12、:18 |
| issue-analyzer | 保留：已交付文本日志包、时间点与问题描述；GB 是规模情形，不是最低输入要求。上游/issue-analyzer/README.md:18；上游/issue-analyzer/SKILL.md:36 | 降级为给工程师的命令：缺日志时给清单和采集命令；已给日志直接分析。上游/issue-analyzer/SKILL.md:68、:135 | 保留：清单、扫描、时间线、原文回验；删独立绕过 diagnose 的确诊与 fix 路径。上游/issue-analyzer/SKILL.md:48、:53、:76 | 保留 Markdown 与 evidence.json；证据回验不是根因验证。上游/issue-analyzer/SKILL.md:53、:72 |
| cluster-analysis | 保留：一份单卡/多卡 Prof 或已有集群结果。上游/cluster-analysis/SKILL.md:3、:27 | 保留离线解析；README 的 Profiler/msprof 采集说明降级为给工程师的命令；迁入流程不采新数据。上游/cluster-analysis/README.md:54 | 保留 advisor、recipe、泳道与定位；限制 rank、step/window 范围，不把通信占比当确诊。上游/cluster-analysis/SKILL.md:10、:29 | 保留 workflow 状态、定位 JSON、HTML；迁移所有写点。上游/cluster-analysis/SKILL.md:14、:30、:36 |
| cluster-compare | 保留：A/B 两份集群 DB 或 TEXT，声明基准方向。上游/cluster-compare/README.md:32、:69 | 保留已有包离线生成；删自动安装。Level1 等采集要求降级为工程师说明。上游/cluster-compare/README.md:52、:61 | 保留差异、有效吞吐和贡献度；对齐采集范围后才能解释。上游/cluster-compare/SKILL.md:302、:304 | 保留 HTML/MD、单集群 JSON与进阶 JSON；取消输入目录默认写点。上游/cluster-compare/README.md:73、:82 |
| prof-compare | 保留：两份单卡 Prof 或已有 compare xlsx；指定基准与对比。上游/prof-compare/SKILL.md:23、:44、:61 | 无新增现场采集主步骤；保留离线 compare，删自动 pip。上游/prof-compare/SKILL.md:51、:53 | 保留各 Sheet 判读，先核对 step 与单位。上游/prof-compare/SKILL.md:59、:116 | 保留 JSON、HTML、中文 xlsx；缺 Excel 依赖时明确不可分析该输入。上游/prof-compare/SKILL.md:64、:193 |
| cpu-host-performance | 保留：采集包、ftrace、原生 JSON；缺调度证据明示。上游/cpu-host-performance/README.md:69 | 降级为给工程师的命令：sudo 采集；删 agent 的 apply/watch/rollback 与现场 PID 发现。taskset 仅交付建议。上游/cpu-host-performance/SKILL.md:19、:21、:48 | 保留离线解析及至少两类独立证据约束；不由 CPU 高单独判断。上游/cpu-host-performance/SKILL.md:94、:95、:115 | 保留 HTML、report_data.json；bind_cpu.sh 改成待核验建议附件，禁止自动执行。上游/cpu-host-performance/SKILL.md:12、:107 |
| ibmc_analyzer | 保留：dump_info、机器目录或已采集压缩包，多机可比。上游/ibmc_analyzer/SKILL.md:18 | 保留本地解包，无现场采集步骤；解包不是对客户机器采集。上游/ibmc_analyzer/SKILL.md:80 | 保留解析、当前与历史事件交叉检查；优先级不直映射严重度。上游/ibmc_analyzer/SKILL.md:138、:151、:188 | 保留每机/汇总 JSON 与 HTML，摘要带缺失文件清单。上游/ibmc_analyzer/SKILL.md:90、:120、:148、:162 |
| vllm-ascend-tuning | 改为保留已交付模型、硬件、配置、版本与 benchmark 结果；删 SSH 可访问性要求。上游/vllm-ascend-tuning/README.md:20 | apt、写 governor、在线 bench 与本地吞吐 bench 均降级为工程师实验命令；删 agent 执行。上游/vllm-ascend-tuning/SKILL.md:1029、:1089、:1459、:1539 | 保留配置审核与同负载结果比较；未实验不声称收益。上游/vllm-ascend-tuning/README.md:18、:29 | 保留配置建议、验证与回退计划；新增结果 JSON，未交结果时不生成「已调优」结论。上游/vllm-ascend-tuning/README.md:29 |

## 3. 逐 skill 改动表

所有表都是拟改动清单。代码未执行，依赖兼容、真实报告效果与资源上限均未验证。

### ascend-dump-analyzer

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/ascend-dump-analyzer/SKILL.md:3、:24 | description 限定「已有环境快照分析/配置漂移」；采集段移到按需工程师指引 | 不接管客户服务器；明确点名仍可触发 |
| 上游/ascend-dump-analyzer/SKILL.md:15、:46 | 保留离线版本检查；记录规则版本、读取失败、UNKNOWN 和角色范围 | 缺字段不等于环境异常；规则不匹配不等于事故根因 |
| 上游/ascend-dump-analyzer/SKILL.md:18 | 输出改为会话专属 evidence 目录，统一生成摘要与结果清单 | 避免通用 outputs 覆盖及跨单混用 |
| 上游/ascend-dump-analyzer/README.md:7；上游/tests/ascend-dump-analyzer/test_p1.py:13 | 分离离线脚本和采集器；测试从顶层 tests 纳入发现，采集测试不进入离线执行集 | 上游测试并非全在 skill 自己目录；不能整目录盲搬 |
| 上游/ascend-dump-analyzer/SKILL.md:24 | 保留标准库采集器的来源说明；迁入诊断不自动装包，离线检查缺运行环境就返回缺依赖 | 标准库描述针对采集脚本，不扩张成所有离线组件无依赖的保证 |

### issue-analyzer

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/issue-analyzer/SKILL.md:3、:38 | description 只接「已交日志包取证」；保留 >2 MB 或 >10000 行先脚本处理 | 「训练中断」泛症状归 diagnose；大输入靠扫描器裁剪 |
| 上游/issue-analyzer/SKILL.md:14、:42 | 保留零第三方依赖脚本；analysis_out 放到专属输出根；离网照常分析已有文本 | 不需要为了迁移引入 pip；运行环境不足则给最小日志裁剪指引 |
| 上游/issue-analyzer/SKILL.md:48、:53、:100 | 保留原文/行号/时间戳回验；根因与修复交回 diagnose | verify 只证明引文存在，不能证明因果成立 |
| 上游/issue-analyzer/SKILL.md:68、:112 | 采集命令只交工程师；computer:// 改为 harness 可展示的绝对路径 | 采集责任与报告可访问性需要分别处理 |

### cluster-analysis

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/cluster-analysis/scripts/run_workflow.py:266、:399、:408、:420 | 贯穿显式 output/work 根；原生 cluster、fallback、recipe、缓存都不得推导输入旁路径 | 单改 --output-dir 不够；当前原生 cwd=root，fallback 也收 root |
| 上游/cluster-analysis/references/pipeline.md:118、:123 | 保留能力探测与 --no-native；固定支持的 CLI 版本和子命令形状；不自动安装 | 与 prof-compare 的 pip 行为区分；原生不可用才用有证据覆盖的 fallback |
| 上游/cluster-analysis/README.md:23；上游/cluster-analysis/SKILL.md:10 | 离网使用已预装依赖；DB/TEXT/事件缺口逐项返回 unsupported/partial | fallback 不是完整原生替代；缺时间证据不能生成虚构 step |
| 上游/cluster-analysis/scripts/report_generator.py:821；上游/cluster-analysis/scripts/recipe_fallback.py:492 | Wait/Transit 等规则只产候选解释与数值，不直接写链路/慢卡根因 | 当前报告把比较结果直接解释成原因；必须补独立证据 |
| 上游/cluster-analysis/SKILL.md:50；上游/cluster-analysis/tests/test_regressions.py:15 | vendor 子实现固定版本；先保留桥接边界，后统一 prof-compare；测试改为隔离导入 | 当前 sys.path 同时插入两个 scripts，直接平铺会污染导入 |
| 上游/cluster-analysis/README.md:24；上游/cluster-analysis/SKILL.md:14 | 不继承默认多 agent 波次；按需阶段执行，保留完整报告请求的阶段契约 | 自动诊断只读本次缺口；完整报告与局部取证须标不同覆盖范围 |

### cluster-compare

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/cluster-compare/README.md:52 | 自动 pip 改为只探测依赖与版本；缺工具时接受已导出的 DB/TEXT，或请工程师在预配环境导出 | 离网/内网不临时访问 PyPI，不把装包混入诊断 |
| 上游/cluster-compare/scripts/cluster_data_extractor.py:214、:286、:676 | SQLite 只读打开；advanced_work 显式放入输出根；CLI 参数必须由统一入口传入 | 只读输入要落实到打开方式和所有子命令 |
| 上游/cluster-compare/README.md:79、:82 | 单集群 MD 和默认 A 目录报告都迁到会话输出目录 | 报告与缓存不能写在现场数据旁 |
| 上游/cluster-compare/templates/cluster_compare_report.html:7 | 去掉外部字体；图表脚本固定版本随包分发，或降级静态表 | 当前 Tailwind、ECharts、字体需网络，不能称完全离线 |
| 上游/cluster-compare/SKILL.md:302、:304、:310 | JSON 记录有效吞吐公式、贡献度不可用原因、10% 异常阈值与范围；报告只渲染同源 JSON | 避免 HTML 与摘要各算一遍；10% 是工具规则，不是通用故障标准 |

### prof-compare

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/prof-compare/scripts/run_compare.py:104、:110、:223 | 删除执行路径上的 pip_install；迁移过渡调用必须带 --skip_install；缺依赖返回结构化原因 | 仅改 SKILL 文案拦不住代码默认安装 |
| 上游/prof-compare/scripts/main_analyzer.py:23；上游/prof-compare/scripts/csv_translator.py:13 | openpyxl 纳入预配依赖；离网预装固定 wheel；缺失时返回 blocked，提示外部生成 JSON/报告 | 已有 xlsx 仍依赖 openpyxl，不能声称无需依赖即可退化 |
| 上游/prof-compare/scripts/run_compare.py:217；上游/prof-compare/SKILL.md:59 | 强制绝对输出目录；记录 A/B 与 step 选择，检查可比较性 | 默认当前目录不可追踪；多 step 混合会改变差异含义 |
| 上游/prof-compare/SKILL.md:193、:202 | 保留结果格式与 Sheet 分析；结论携带原始指标位置、单位和分析器版本 | 差异报告提供证据，不替代 case 检查 |

### cpu-host-performance

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/cpu-host-performance/SKILL.md:19、:21、:48 | 自动路径只留 analyze；现场 plan/apply/watch/rollback 均移出，采集与 taskset 仅工程师指引 | 现场只读发现也访问客户进程；回滚也是机器变更 |
| 上游/cpu-host-performance/scripts/cpu_trace_collect.sh:1244；上游/cpu-host-performance/SKILL.md:53 | 采集副作用、权限、buffer 成本写入按需说明，不在 agent 本机试跑 | ftrace/debugfs 路径属于现场状态，不因名称叫采集而只读 |
| 上游/cpu-host-performance/SKILL.md:94、:115 | 保留离线入口与独立证据要求；调用前核对依赖，缺项不安装；缺外部解码器时只支持已有文本/JSON | 所有格式的依赖闭包尚未验证，不能承诺一个命令离网覆盖全部格式 |
| 上游/cpu-host-performance/SKILL.md:107、:108 | bind_cpu.sh 不挂自动执行入口；输出建议时要求工程师重验实时 PID/线程身份及回退 | 旧采集快照不能代替当前 affinity 与进程身份 |
| 上游/cpu-host-performance/tests/test_e2e_pipeline.py:7 | analyzer/examples 改为命名空间包；离线合成样本测试保留，现场 shell 测试另组隔离 | 防止根 tests 导入不到包；禁止 CI 触碰真实主机配置 |

### ibmc_analyzer

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/ibmc_analyzer/scripts/run_bmc_report.py:60、:69、:71 | 安全解包：路径不得越界，拒绝逃逸链接，限制展开体积；不支持安全过滤就失败 | 旧 Python 分支回落无 filter，不能沿用为默认路径 |
| 上游/ibmc_analyzer/scripts/run_bmc_report.py:95 | 每次调用新建目录；删除跨调用 glob 清理，改为只消费本次 manifest | 当前会删除目录内旧 *_bmc.json；不能让不同会话共用 |
| 上游/ibmc_analyzer/scripts/parse_bmc_collect.py:19；上游/ibmc_analyzer/SKILL.md:87 | 保留标准库解析；预检 Python/SQLite 能力，不新增安装步骤；缺失则保留清单、请求导出文本 | 只读离线能力不等于所有 Python 部署都已验证 |
| 上游/ibmc_analyzer/scripts/generate_bmc_report.py:562；上游/ibmc_analyzer/scripts/parse_bmc_collect.py:37 | 电源判定统一来源：报告条件缺 Vin 上限，解析配置有 264 V；先复核机型规范再统一 | 已发现文本/代码差异，不能直接抽成硬件真值 |
| 上游/ibmc_analyzer/SKILL.md:188；上游/ibmc_analyzer/scripts/generate_bmc_report.py:1247 | P0/P1 等只保留为工具优先级；另由 diagnose 判 severity；温度/分数只作候选 | 工具分级不等于 data-loss-risk；未知不显示成健康 |

### vllm-ascend-tuning

| 文件:行号 | 改成什么 | 为什么 |
|---|---|---|
| 上游/vllm-ascend-tuning/README.md:26；上游/vllm-ascend-tuning/SKILL.md:5 | description 限定点名的配置评审与已有基准结果分析；去掉 SSH 要求 | 「吞吐不足」仍由 diagnose 接单；不复刻现场调优 agent |
| 上游/vllm-ascend-tuning/SKILL.md:1029、:1055、:1089、:1693 | apt/pip、governor 与工具安装退出自动流程；只交带前提、副作用和回退的工程师命令 | 内网安装属于环境准备，不由诊断临时执行 |
| 上游/vllm-ascend-tuning/SKILL.md:1459、:1539 | 在线与离线 benchmark 都改为工程师实验；分析器只读返回结果 | 「离线吞吐测试」仍运行模型占设备，不等于离线材料分析 |
| 上游/vllm-ascend-tuning/README.md:16、:29 | 模型配置按版本拆成按需支撑文件；输出待验证组合、目标指标与反证条件 | 上游「已验证」标签的跨环境效力未验证，不承诺提升 |

### 共用布局、测试与先验提炼

拟保留每个 `skills/<name>/SKILL.md` 为入口；离线脚本放其 `scripts/` 或命名空间包，模板放 `assets/`，流程细节放同 skill 的 `references/`。根 `references/` 只放经审核的先验，不放 Python 分析器。

依据：`skills/diagnose/SKILL.md:14`、`references/_types.yaml:23`。

拟在根 `scripts/` 放一份共用本地执行入口，负责路径、预算、依赖和结果协议；各 skill 只给参数。依赖按分析器分别固定版本与来源校验值，在准备环境时安装。离网用预置 wheel，内网用已批准镜像；运行时均不安装或升级。依据：上游/prof-compare/scripts/run_compare.py:104。

拟把离线测试迁到根 `tests/test_tool_<name>_*.py`，或可被 unittest 递归发现的包；保留测试含义，重写路径定位。禁止把八份 scripts 依次塞入全局 sys.path。暂不能包化的测试用独立 Python 进程，明确 cwd 与模块根。

依据：`.github/workflows/kb-checks.yml:458` 使用 `python3 -m unittest discover tests`；上游/cluster-analysis/tests/test_regressions.py:15 同时插入本地与 vendor 路径，`:24` 还依赖 openpyxl。未来需补 CI 路径过滤，不能只保证本地 discover 可跑。

验证用合成数据覆盖只读输入、缺依赖、格式不支持、超时、A/B 方向、单位与缺数据；BMC 补危险解包样本。现场采集/绑核测试不随离线测试执行。真实客户包不入公开测试目录。依据：`docs/spec/design-principles.md:45`、`:75`。

拟每份 description 只写数据形态、用途与排除项，目标 ≤120 个中文字符；SKILL 正文目标 ≤150 行，详细流程按需加载。这是本方案预算，未验证其触发质量。不得把八份正文内联到 diagnose。依据：`CLAUDE.md:27` 起的加载说明、`docs/spec/design-principles.md:129`。

所有必需行为必须随 skill 分发；`docs/` 只作可选论证。门禁与摘要格式要写在入口可达的支撑文件，不能只链接设计文档。删除 ADR 号、日期与卡号；版本号及命令原值保留。依据：`.github/workflows/kb-checks.yml:611`、`:622`，`docs/spec/writing-norms.md:1` 起的共用规范。

以下是本次已定位的 10 个候选提炼单元，不是全库最终新增数。先检索现有 reference，同用途面追加；未去重、未核对官方依据，均未验证，当前可直接发布的已验证词条数为 0。

| 来源 | 可提炼单元与拟类型 | 数量 | 不能据此发布什么 |
|---|---|---:|---|
| 上游/ascend-dump-analyzer/SKILL.md:46、:48 | 快照覆盖与角色可比性，tool | 1 | 不把字段相似度写成根因置信度 |
| 上游/issue-analyzer/SKILL.md:48、:53 | 引文回验输入/输出与限制，tool | 1 | verify 成功不能生成故障模式因果表 |
| 上游/prof-compare/SKILL.md:59、:116 | compare 的 step、Sheet 与单位解读，tool | 1 | 单次差异不能生成普适性能阈值 |
| 上游/cluster-compare/SKILL.md:302、:304 | 有效吞吐与贡献度的解读，tool，同用途面合一 | 1 | 10% 慢卡线索不是硬件故障事实 |
| 上游/cpu-host-performance/SKILL.md:94、:108 | 离线 Host 证据限制（tool）；taskset 副作用与回退（command-side-effect） | 2 | 不把两类证据要求写成已验证准确率 |
| 上游/ibmc_analyzer/SKILL.md:153；上游/ibmc_analyzer/scripts/generate_bmc_report.py:562、:715、:946 | 当前/历史告警复核（methodology）；机型限定的传感器规则（tool） | 2 | 180/264 V、7000 RPM、42/95°C 未核原始规范，不发 platform-fact；健康分数与 UI 颜色留代码 |
| 上游/cluster-analysis/scripts/recipe_fallback.py:181、:466、:492；上游/cluster-analysis/scripts/report_generator.py:821 | recipe 规则与适用限制，tool，合为同用途面 | 1 | max/min>1.2、样本四分位、占比>0.5 是实现启发式；不能写成带宽/慢卡根因标准 |
| 上游/vllm-ascend-tuning/README.md:18、:29 | 同负载基准结果比较流程，methodology | 1 | 模型配置、安装配方与版本相关参数不自动升格为通用最优配置 |

HTML 拼接、图表颜色、排序、Top-N 截断、xlsx 读取、DB 适配和分位数算法保留代码与测试。根 reference 解释方法及限制，不复制完整实现。报告中的判断应先产入结构化结果，再由 HTML 渲染，避免隐藏第二套规则。

依据：上游/cluster-analysis/scripts/report_generator.py:801、上游/ibmc_analyzer/scripts/generate_bmc_report.py:562。

先验来源不能把个人仓库冒充 official-doc。需取得可追溯的工程师输入，或核对其引用的官方原文，再按真实来源标注；case-derived 的 methodology 还需至少 3 个已升格 case。字段需含来源、验证日期和状态，平台规则另写适用范围。

依据：`references/README.md:31`、`:45`、`:57`、`:76`；`references/_types.yaml:36`、`:67`。

## 4. 调用与契约方案

采用两个入口、同一执行契约。分析器只提取事实和候选解释，诊断主持 agent 负责收敛、验证、fix、severity 和 trace。现有两阶段 case 加载不变。依据：`skills/diagnose/references/diagnosis-procedure.md:168`、`:184`、`:223`。

### diagnose 接线点与返回位置

步骤 1 登记材料绝对路径、类型、范围与缺项；需要大包取关键事实时只调用轻量清单/提取模式。BMC 告警、环境版本和日志签名可作为事实返回步骤 2，不能由此宣布根因。依据：`skills/diagnose/SKILL.md:76`，上游/issue-analyzer/SKILL.md:85。

完整分析放步骤 5：Tier 2 未命中，或已有证据不足以解释问题时按下表选择一个分析器。步骤 3 的候选验证缺少具体指标时，可复用同一转接入口仅取指标，然后返回该候选的 quickly_check；不能为取数而把「缺数据」记成「已排除」。依据：`skills/diagnose/references/diagnosis-procedure.md:202`、`:243`。

| 已确认的数据形态与意图 | 选择 | 拒绝或补问条件 |
|---|---|---|
| 一次 Prof 采集，单卡或多卡；或一份集群输出 | cluster-analysis | 明确是两次采集比较则不用此入口。依据：上游/cluster-analysis/SKILL.md:3、:36 |
| 两份 Prof，各自单卡；或 compare xlsx | prof-compare | xlsx 必须是 compare 结果；两份目录不能仅凭数量判单卡。依据：上游/prof-compare/SKILL.md:13、:57 |
| 两份集群采集/结果，各含多 rank 或集群 DB/TEXT | cluster-compare | 先明确 A/B、同负载、rank/step/window；不可比时只交描述差异。依据：上游/cluster-compare/README.md:32、:64、:69 |
| dump_info 或 BMC 一键包 | ibmc_analyzer | 不接 OS 日志；检查内容，不依赖压缩包名称。依据：上游/ibmc_analyzer/SKILL.md:3、:18 |
| 环境 dump JSON、配置快照 | ascend-dump-analyzer | 普通日志不是环境快照。依据：上游/ascend-dump-analyzer/SKILL.md:14、:46 |
| plog/slog/framework/dmesg 等日志包 | issue-analyzer | 时间窗缺失只扫描，不推断跨机事件先后。依据：上游/issue-analyzer/SKILL.md:8、:48；skills/diagnose/references/diagnosis-procedure.md:304 |
| ftrace/Host 采集包，目标是调度证据 | cpu-host-performance | 只有环境 JSON 时只给环境分析，不给调度根因。依据：上游/cpu-host-performance/README.md:69 |
| vLLM 配置与已有 benchmark，明确请求调优评审 | vllm-ascend-tuning | 不按「慢」自动触发在线实验。依据：上游/vllm-ascend-tuning/README.md:20、:29 |

不增加第三个 triage 维度。数据形态是取证能力选择，不决定 namespace；性质仍只有 interrupt、precision、performance。diagnose 骨架加一句转接规则，详细表放其支撑文件。

依据：`triage-tree.d/00-protocol.md:7`、`:31`；`triage-tree.d/10-interrupt.yaml:8`、`triage-tree.d/20-precision.yaml:6`、`triage-tree.d/30-performance.yaml:8`。

分析完成后，主持 agent 核对结果范围和原始证据。出现新签名时回步骤 2/3；命中候选仍跑 quickly_check、diagnosis checks。步骤 5 新根因没有现成 case 时，按假设—反证—工程师验证收敛，不能伪造 quickly_check 通过。fix 只能由主持者经严重度规则交付。

依据：`skills/diagnose/references/diagnosis-procedure.md:184`、`:223`、`:243`；`skills/diagnose/SKILL.md:159`。

### 手动 invoke 与会话归属

description 统一句型：「分析已提供的〈数据形态〉，用于〈专门用途〉；支持点名〈skill 名〉；泛症状由 diagnose 接单。」八项具体形态采用上表，不加入「训练很慢」「服务异常」等宽触发词。对没有数据的咨询只解释方法，不开诊断单。依据：`skills/diagnose/SKILL.md:20`。

点名且提供材料时，入口先检查当前活动诊断：同一问题复用 session；否则调用现有 `trace_begin.py` 建单，再运行分析，不要求用户先输入 /diagnose。手动入口中的主持 agent 代行同一记账与验证流程，分析器 Python 不写 trace。依据：`skills/diagnose/references/diagnosis-trace.md:424`。

纯报告请求只完成取证与报告，不强行扩成根因诊断；trace 明示「分析完成，根因未验证」，不得因为 HTML 生成成功记 resolved。后续请求修复时续用同单进入验证。所需状态映射要在实施时核对 `trace-status.yaml@57f02ecc5adcf790a962e8ef0b80c9af6100f5cf`，本次未验证，不能自造终态。

### 输入、输出、预算与失败

输入契约拟为本机绝对路径数组、用途、A/B 标签、session_id、显式输出根与预算。附件先由 harness 落本地，再传路径；无法落地则返回缺路径，不让 Python 接远端附件链接。数据不上传远端；本地分析机不等于客户目标机。依据：`CLAUDE.md:115` 的客户环境边界；上游/ibmc_analyzer/SKILL.md:18。

输出根拟为 `<状态目录>/traces/evidence/<session_id>/tool-runs/<call_id>/`，状态目录由 `DSH_SLEUTH_STATE_DIR` 解析（见 8.5）。每次调用独立目录，包含输入清单、状态、日志、结构化结果和报告；原始数据只读，副本/解包也放此处。依据：`CLAUDE.md:106` 起的 worktree 约束。

统一结果 JSON 拟含 schema_version、analyzer_version、status、summary、findings、evidence_files、missing、limits、artifacts、duration、exit_code。每条 finding 带原始文件位置、测量值/单位、窗口、规则版本与「事实/候选/未验证」标签。

状态取 ok/partial/blocked/failed，仅属工具结果，不复用诊断终态。

模型默认只接 ≤500 个中文字符摘要、最多 5 条关键发现和绝对证据路径；结构化短返回拟限 8 KiB，超额落文件。摘要先写覆盖与失败，不因截断丢失缺项。HTML 只给用户链接，默认不读进上下文；需要复核时按 JSON 证据定位原文。预算依据：`docs/spec/design-principles.md:129`，具体数值为提议。

执行预算拟默认 10 分钟、4 GiB 进程内存、20 GiB 展开空间、10 万文件；上线前用代表包校准，当前未验证。超限返回 blocked/partial，列出可拆分的 rank/时间窗。不能先解包再检查体积，不能截断后报告「未发现异常」。依据：上游/issue-analyzer/SKILL.md:36；`docs/spec/design-principles.md:141`。

缺依赖返回依赖名及所需版本，不 pip/apt；超时停止本次进程树并保留已完成产物；格式/版本不支持列能力边界；无数据给最小补料清单。参数错误可修正一次，工具失败不重复跑相同输入。退回原诊断路径，不把失败计为排除 case。依据：`skills/diagnose/references/diagnosis-procedure.md:300` 的失败区分思路。

拟由共用执行入口检查只读打开、输出越界、子进程超时与结果 schema；这些是待实现的程序检查。根因判断、可比性和 severity 仍是语义约定，不能宣传为已有硬门。依赖工具的完整写行为未审计，不在首批验收前声称只读得到保证。依据：`docs/spec/design-principles.md:45`、`:51`。

### trace 与 vllm-kb 先例

复用 vllm-kb 的职责分层：仓库写何时调用、怎样读结果和怎样退化；执行入口负责能力探测、预算和截断；不把部署地址写进 trace。依据：`dsh-plugins/dsh-sleuth-vllm-kb/README.md:36`、`:53`。

不能直接复用其 HTTP 调用协议：本次需要本地路径、长任务、子进程、解包、依赖版本及大文件产物；先例是有界远端检索。也不能把四种 external_lookup capability 偷换成八个分析器。现有枚举见 `skills/diagnose/references/diagnosis-trace.md:75`。

拟新增 tool_analysis 事件及配套校验/统计，字段包含 entry（manual/diagnose）、call_id、capability、analyzer_version、input_manifest、status、duration、result_file、used_findings、reason。主持 agent 每次调用记一次；Python 只落执行结果。

已有 external_evidence 开关不用于本地分析器。

这不是现有 trace schema。实施必须同时改词表、校验、回放、统计和手动报告状态映射；未完成前不开放自动接线。用成功率、超时率、证据采用率、误选率区分「工具故障」「调用错误」「判断错误」，不能把工具成功计作诊断解决。

依据：`skills/diagnose/references/diagnosis-trace.md:1`、`:84`；`docs/spec/design-principles.md:117`。

## 5. tradeoff 表

A 为仅 diagnose 自动调用，B 为仅手动调用，C 为两条入口共用契约。逐项结论如下；比较是基于文件结构的设计判断，触发率、耗时和准确率未实测。

| 维度 | A | B | C | 本项选择与依据 |
|---|---|---|---|---|
| 上下文成本 | 可不注册八个公开入口，常驻最省；自动转接要读选择规则 | 八份 description 常驻，用户点名后只读对应正文 | 八份短 description 常驻，加一份按需选择表；禁止双份正文 | 单项选 A 最省；总体接受 C 的摘要成本，以 ≤120 字/入口为拟预算。依据：CLAUDE.md:27 起的加载机制 |
| 路由误触 | 泛性能症状自动选错工具的风险需要形态检查控制 | 点名减少泛症状误触，但人仍会把双集群交给单卡工具 | 点名和自动路径都检查输入；混合包只按当前缺口选一个 | 选 C，经同一形态检查；不新增 triage 维度。依据：上游/prof-compare/SKILL.md:3；上游/cluster-analysis/SKILL.md:3 |
| 门禁强度 | 主持者统一检查，责任最清晰 | 独立 skill 报告容易绕过 quickly_check 与 severity | 手动入口复用建单和验证；报告与 fix 分权 | 单项选 A 最简单；C 只有共用检查验收后才可开放，不能仅靠八份提示词。依据：skills/diagnose/references/diagnosis-procedure.md:184、:223 |
| 可观测性 | 同一 trace 易归因，手动需求不可见 | 八处单独记账易缺失，报告成功易误计解决 | 共用事件记录入口、版本、证据采用与失败 | 选 C，可比较两种入口且不漏手动工作；前提是 schema 与统计同步。依据：docs/spec/design-principles.md:117 |
| 维护成本 | 一个入口，仍要维护八套解析依赖 | 不改 diagnose，但八份入口各有生命周期 | 共用适配器加两类入口测试，成本最高；分析代码只留一份 | 单项选 A；总体 C 接受额外入口测试，版本统一清单管理。依据：上游/cluster-analysis/SKILL.md:50；上游/prof-compare/scripts/main_analyzer.py:23 |
| 失败模式 | 失败可回主循环，但自动完整分析会拖慢普通问诊 | 人选择运行时机；超大包与缺依赖仍存在 | 共享预算/预检/超时/partial，手动失败也能续接 | 选 C：同一失败协议覆盖两入口；不重试同输入。依据：上游/issue-analyzer/SKILL.md:38；上游/cluster-analysis/SKILL.md:10 |

总体选 C，是为了保留已成立的点名材料分析入口，同时让 diagnose 使用同一能力。A 的低成本成立，但会收回手动入口；B 的隔离性成立，但不能满足主诊断自动取证。C 的代价是共用执行入口和 trace 适配必须先完成；不接受「两套各跑各的」实现。

## 6. 迁移批次与每批的前置条件

按验收条件推进，不按日期推进；各批都能通过关闭入口回退到原 diagnose。原则依据：`docs/spec/design-principles.md:105`、`:153`。

| 批次 | 范围 | 前置条件与验收 |
|---|---|---|
| 准备批 | 来源授权、固定版本、共用执行契约、trace 事件、测试发现 | 作者口头授权已由用户确认；记录授权来源；核对依赖；合成样本证明不写输入、无运行时安装、失败可回主流程 |
| 首批之一 | ibmc_analyzer、prof-compare | BMC 安全解包/新目录隔离、阈值冲突标记；compare 禁 pip、固定 openpyxl/msprof；手动与自动均经过验证门。依据：上游/ibmc_analyzer/scripts/run_bmc_report.py:60、:95；上游/prof-compare/scripts/run_compare.py:104 |
| 首批之二 | cluster-analysis、cluster-compare | 完成所有 output/cwd/cache 写点改造；离线 HTML；native/fallback 覆盖标识；DB/TEXT/单卡/双集群边界测试；vendor 版本关系明确。依据：上游/cluster-analysis/scripts/run_workflow.py:399；上游/cluster-compare/templates/cluster_compare_report.html:7 |
| 第二批 | ascend-dump-analyzer、issue-analyzer | 采集仅工程师说明；dump 角色/版本规则审核；GB 级日志按预算流式裁剪与回验；fix 由主持者交付。依据：上游/ascend-dump-analyzer/SKILL.md:24；上游/issue-analyzer/SKILL.md:38、:53 |
| 第三批 | cpu-host-performance、vllm-ascend-tuning | 离线分析与现场执行入口分离；生产 PID/绑核/采集/benchmark 不在自动调用图；已有基准结果可比性验证；无数据只给计划。依据：上游/cpu-host-performance/SKILL.md:21；上游/vllm-ascend-tuning/README.md:26 |

每批需跑根 unittest 发现与相关测试、skill 自包含检查、无外网报告检查，以及两入口的门禁回放。原生工具在预配隔离环境另做集成验收；本次禁止运行上游脚本，以上均为待执行检查。依据：`.github/workflows/kb-checks.yml:458`、`:605`。

## 7. 待确认

作者口头授权已由用户在本次方案讨论中确认，记为授权依据，不再列为待确认项。以下四项不阻塞方案交付，但阻塞相应迁移验收。

1. 分析运行环境的负责人、Python/msprof/openpyxl 支持版本与离网包来源。未确认则不能给安装清单和兼容承诺，只能返回缺依赖。依据：上游/prof-compare/scripts/run_compare.py:110；上游/prof-compare/scripts/main_analyzer.py:23。

2. BMC 规则对应机型及原始规范的可核查版本。未确认则电压、转速、温度与 ECC 只呈现观测及工具候选提示，不发布平台事实。依据：上游/ibmc_analyzer/SKILL.md:14；上游/ibmc_analyzer/scripts/generate_bmc_report.py:562。

3. 代表性脱敏材料规模及允许的运行预算。未确认则采用本方案试行限制，超限不跑完整分析；10 分钟/4 GiB/20 GiB 的适用性未验证。依据：上游/issue-analyzer/SKILL.md:36；上游/cluster-analysis/README.md:24。

4. 手动报告完成但尚未验证根因时的 trace 状态与统计归属。未确认则不把报告成功记 resolved，也不开放完整自动接线。依据：skills/diagnose/references/diagnosis-trace.md:424；trace-status.yaml@57f02ecc5adcf790a962e8ef0b80c9af6100f5cf。

## 8. 插件打包形态（安装优先）

本节按「打成可安装的 DSH 插件」修订第 3、4 节里按检出写的落点。冲突处以本节为准；第 3 节的逐 skill 改动与第 2 节的四段拆解仍然有效。

### 8.1 一个包，八行开关

一个包，八行开关。八个分析器共用同一套 python 解析、状态目录、结果 JSON 与预算；拆成八个包要把这些复制八份，且回滚单位是一组包（`proposals/pluginization.md:159`），拆开只增加对账。

包内仍按 skill 分目录，回退粒度按行：关掉某一行等于「这个分析器不存在」，诊断回原路径。先例是 `dsh-plugins/dsh-sleuth-vllm-kb/cordis.patch.yml` 的三行开关。

### 8.2 目录布局

```
dsh-plugins/dsh-sleuth-analyzers/
├── package.json            name/version/main、dsh.bundle.patch
├── cordis.patch.yml        八行开关 + 一行工具 + 一行设置
├── index.js                注册 skills provider 与一个主机工具
├── lib/                    python 解析、依赖预检、预算、结果 schema、截断
├── skills/<八名>/SKILL.md  按第 3 节改过的入口与判据
├── upstream-sources/       固定版本上游原文，仅维护时使用
├── overrides/<八名>/       我们改过的文件整份副本，文件头标规则编号
├── constraints.yaml        约束表：每条规则一个编号，覆盖文件与它对应
├── upstream-lock.yaml      来源、路径映射、覆盖文件清单与哈希
├── tools/<八名>/           原文套覆盖文件后的生成物，禁止手改
├── vendor/                 离网 wheel（第 3 节「预置 wheel」的落点）
└── README.md               装、配、验收
```

仓内保留上游原文、覆盖文件与约束表；发布包只带生成后的 `tools/` 与本仓入口，不发 `upstream-sources/`、`overrides/`、`constraints.yaml` 和测试。测试留根 tests。生成物纪律复用面板包，见 `dsh-plugins/README.md:25`、`:103`；只复用生成方式，不宣称面板已实现覆盖文件管理。

### 8.3 包清单与开关

`package.json` 除 `name`/`version`/`main` 外需要 `dsh.bundle.patch`；本仓自定字段按 `proposals/pluginization.md:100` 的约定加 `data_format` 与 `capability_api`，由 `pack_status` 读，DSH 不读。

`cordis.patch.yml` 取十行：`analyzer-<name>` × 8（默认 `disabled`）、`analyzers-run`（默认 `disabled`，注册主机工具）、`analyzers-settings`（默认启用，只提供设置节）。

### 8.4 入口是一个主机工具，不是八份执行脚本

注册一个工具（拟名 `sleuth_analyze`），参数为 `analyzer`、`inputs`（本机绝对路径数组）、`purpose`、`ab`、`session_id`、`out_root`、`budget`。工具负责解析 python、预检依赖、跑 `tools/<name>/` 入口、超时后结束进程树、写结果、返回摘要。

理由：八份执行脚本会把预算、截断与结果 schema 各写一遍；一个工具让第 4 节的契约只有一处实现。`ascend-panel` 已经在主进程里 spawn python 并处理 Windows 上的解释器解析（`dsh-plugins/ascend-panel/panel-host.js:1830`），这条路有先例。

### 8.5 输出根改由状态目录解析

第 4 节把输出根写成主检出下的绝对路径，插件形态下改为由 `DSH_SLEUTH_STATE_DIR` 解析：

`$DSH_SLEUTH_STATE_DIR/traces/evidence/<session_id>/tool-runs/<call_id>/`

主机工具在进程内用 `node:fs` 写任意路径，不受 `workspace-write` 栅栏（`proposals/pluginization.md:99`）。因此分析产物这一条不要求把整个会话切成完全访问；5.6 那条约束仍适用于 agent 自己写 trace 的路径。

### 8.6 先验证一件事，再搬代码

主机工具 spawn 的 python 是否受会话沙箱约束，未验证。`dsh-plugins/ascend-panel/panel-host.js:138` 记录过沙箱把子进程挡在启动之前（`0xC0000142`）。

最小验证：装一个只有 `index.js` 与一个工具的包，工具里 spawn `python3 -c "print(1)"`，在 `workspace-write` 与完全访问两档各跑一次，记退出码与 stderr。这是首批第一个验收项，先于任何代码搬运——不通过时包仍可安装，但「装上就能跑分析」不成立。

### 8.7 插件形态的首批验收

1. 装包：插件页粘贴目录或 `plugin_manager install_bundle`，重启后技能目录出现八个名字。
2. 开关：关 `analyzers-run`，工具消失、诊断走原路径；再开，工具回来。
3. 工具：对一份合成 BMC 包跑一次，结果 JSON 落在状态目录，摘要 ≤500 字。
4. 降级：把 python 从 PATH 摘掉，工具返回 `blocked` 与依赖名，不是超时或空结果。
5. 卸载：删包后状态目录里的 `tool-runs` 仍在，面板按缺件显示，不显示 0。

## 9. 上游更新与维护归属

建议先由上游维护通用分析实现，sleuth 维护诊断入口、适配器和发布包；更新按固定提交引入，不跟随上游主分支自动生效。若作者愿意转移维护责任，再按分析器逐个切换主仓。以下为拟定流程，尚未实施。

本节补充第 3 节的迁入方式和第 8 节的插件发布。依据是可回退与可观测要求：`docs/spec/design-principles.md:105`、`:117`；包版本与来源记录沿用 `proposals/pluginization.md:83`、`:163` 的提议。

### 9.1 三种维护方式怎么选

| 方式 | 收益 | 代价与成立条件 | 结论 |
|---|---|---|---|
| 上游维护实现，sleuth 固定版本适配 | 作者继续原工作流；通用修复可供两边使用 | sleuth 需有人负责更新评审、覆盖文件与回归；不能只复制一次 | 当前选用。调用差异已存在，例如自动安装：上游/prof-compare/scripts/run_compare.py:110 |
| 作者转到 sleuth 维护实现与入口 | 同一变更可同时修改代码、契约和测试，减少同步 | 需作者同意、明确评审责任和发布责任；原仓对应目录停止独立修改 | 作者愿意长期维护时可选；可先转一个分析器，不能要求八个一次迁完 |
| 两边都独立开发，再双向同步 | 各自发布自由 | 同一文件出现两套修复、阈值和回退历史，需持续判断保留哪边语义 | 不选；不利于错误归因，依据：docs/spec/design-principles.md:117 |

作者转来贡献 PR 与转移主仓是两件事。作者可以直接修改 sleuth 的适配器；通用解析修复仍回上游。只有约定某分析器的主仓改为 sleuth，后续通用实现才以 sleuth 为准。作者已口头同意迁入与再分发，授权按「用户确认」记；长期维护意愿与转移主仓尚未讨论，本次只确认授权，不假设维护承诺。

### 9.2 迁入时为后续更新保留什么

拟用 `upstream-lock.yaml` 逐分析器记录稳定标识、仓库、固定 commit、依赖版本、覆盖文件清单、上游议题与授权来源。授权写「作者口头授权，用户确认」，不虚构许可名称。包清单另记适配器、结果协议和构建版本。依据：本次用户确认；`proposals/pluginization.md:83`。

`upstream-sources/` 留按清单选入的上游原文，逐字节保留，只随来源版本升级；`overrides/` 留我们改过的文件整份副本，没改的文件不复制。拟新增 `scripts/build_analyzer_bundle.py`，把覆盖文件套到原文上生成 `tools/`，支持 `--check`；诊断和安装不构建。脚本尚未实现，检查方式参照 `scripts/build_panel_bundle.js:26`。

取源仍在仓库外克隆，审核后把选定原文纳入仓内；构建只读仓内原文与覆盖文件，可离网复现。本次研究不复制上游。生成物由构建生成，不手工进 PR；主干生成与发布规则需纳入生成物检查。依据：CLAUDE.md:125；本次用户要求。

清单逐文件存 `upstream_path → source_path → output_path`，分别为上游路径、原文路径和 tools 产物路径，另存 blob 哈希、稳定分析器标识及依赖关系。新建文件以 upstream_path 为空标注，不冒充上游原文件；共享源可映射多个产物，但分别列出消费者。

边界按路径定：凡改变 `tools/` 内容的本地修改，一律算上游实现适配，必须在 `overrides/` 留文件并在 `constraints.yaml` 挂一条规则编号；新增、删除、模板与内置规则同算。改本仓入口、说明、配置不算，但不得用生成器里的临时替换绕开覆盖文件。纯路径映射由清单记录，上游原文升级由来源提交差异记录。

生成检查需验证原文哈希、覆盖文件与 tools 三方一致，再比 `tools/`；未登记的差异拒绝发布。另加两条：每个覆盖文件头写的规则编号必须在 `constraints.yaml` 里存在；`constraints.yaml` 每条规则要么挂了覆盖文件，要么写明这条不需要改代码。覆盖文件头记原因、目标文件、测试与回提状态。面板现有检查也区分「重新生成一致」与「保留源内容」，见 `scripts/check_panel_bundle.js:729`。

sleuth 自己的 SKILL.md 不被上游覆盖。上游入口文本作为变更审阅材料：新增输入、算法约束和输出要同步评估，sudo、安装、在线实验与泛症状触发词不能随更新恢复。原有风险实例见上游/cpu-host-performance/SKILL.md:21、上游/prof-compare/scripts/run_compare.py:104。

覆盖文件尽量只改无法由适配器控制的行为；可配置输出目录、禁安装开关、统一 JSON 和安全解包这类通用改动可提议上游接收。上游接收后，在对应版本升级时删除该覆盖文件并重跑回归；不永久维护两份等价修改。

### 9.3 每次上游更新怎么适配

拟用以下流程更新；发现新提交只产生候选，不改变已安装版本。维护者可在需要功能或修复时手动发起；定时发现仅在另行配置后启用，本次不创建自动任务。

1. 在仓库外取候选提交，对旧新完整目录树做差异检查；按映射核对源路径与哈希，并递归枚举 vendor 中的 SKILL.md。映射源消失、新增未归属 skill 或重名候选必须报告；Git 改名检测只给候选，确认新映射后才更新。
2. 沿 imports、子进程、模板与 vendor 引用扩展受影响集合；把差异分成接口、算法/阈值、副作用、依赖、报告与文案。记录迁入或跳过原因；原路径仍在但实现被挪到 vendor 时，也要更新依赖映射，不只检查路径存在。
3. 在 worktree 中更新固定来源与覆盖文件：每个覆盖文件做三方比较（旧上游 / 新上游 / 我们的版本），按 `constraints.yaml` 对应规则重写。新上游改动了同一段时停止改写，交人工判断。输出路径、禁安装与现场动作边界必须重新检查。依据：CLAUDE.md:105。
4. 同一组合成材料分别跑旧版、新版；比结构化事实、覆盖、证据指针、阈值和失败状态，不比较整份 HTML 字节。新增格式补样本；预期结果变化要写原因，不能只把断言改成新版输出。
5. 跑本次受影响的测试，再跑共用契约及两入口回放；检查缺依赖、超时、只读输入、无外网报告与根因门禁。新增依赖另在预配环境验收。依据：.github/workflows/kb-checks.yml:458；本方案第 4 节契约。
6. PR 同时交来源更新、适配改动、测试与兼容说明；审核通过再发插件新版本。保留旧发布包，部署升级单独执行。严重缺陷可先禁用对应行，不能等待所有分析器一起升级。

若 A 分析器调用 B 的 vendor 副本，两者版本关系要显式记录。一次只更新受影响集合，但不能漏掉共享执行器和依赖它的入口。当前存在 vendor 桥接，见上游/cluster-analysis/SKILL.md:50；其与独立 prof-compare 的版本一致性未验证。

### 9.4 阈值、先验与回滚分别处理

代码中的阈值更新只证明作者改了实现，不证明新阈值适用于所有平台。关联 reference 先标出受影响条目，补来源与适用范围后走独立审核；不随代码同步自动改 active 词条。依据：references/README.md:112；上游/ibmc_analyzer/scripts/parse_bmc_collect.py:37。

拟由同一来源清单记录「代码规则位置 → reference 标识」的关系；规则移动或删除也触发复核。尚未提炼的规则只更新工具版本与限制说明。报告与 JSON 必须使用同一规则结果，防止再次出现电压判断差异，见本方案第 3 节 ibmc_analyzer 改动表。

每次执行记录插件版本、上游 commit、适配器版本与结果协议版本；旧结果保留原版本标记，不被新版本覆盖。会话中的新调用若换版本必须显式记录；前后指标不可比时不直接计算改善率。依据：proposals/pluginization.md:163、:167。

回滚恢复已验收的包及依赖组合，状态目录与旧报告保留；若同时升级核心协议或知识格式，按兼容组合回退，不能只退某个 Python 文件。单包开关只是停止该能力，不是恢复旧版分析行为。依据：proposals/pluginization.md:153、:159。

### 9.5 何时改成作者在 sleuth 主导维护

每个分析器报告改动比例 `R=(A+D)/L`：A、D 为固定上游原文与套上覆盖文件后成品的最终新增/删除行数，L 为该分析器映射选入的上游运行时文本总行数。替换一行计一增一删，不累加历史差异；纯改名不计。此定义落实本次用户提出的 20% 提醒线。

分母包括代码、模板和运行时规则；排除测试、示例、离网 wheel、二进制及 sleuth 自有入口。新增 tools 文件计入 A，整文件删除计入 D；共享源在每个消费者内只计一次。二进制改动单列，L=0 报不可计算；R 可超过 100%，不截顶。

每次更新报告 A、D、L、R、距 20% 的百分点及上次 R；映射范围变化另列分母变化，防止扩大选入目录稀释比例。`R>20%` 必须评审回提作者或接管，并记录决定、责任人与后续动作；它不自动阻断发布，也不自动转移主仓。当前未迁入，比例未测，不填 0。

转移前需约定：哪个分析器以 sleuth 为主仓；谁审算法与诊断边界；谁维护依赖、测试与发布；原仓如何说明新入口。作者负责算法，sleuth 维护者负责诊断契约，跨两面的改动由双方评审。未明确负责人就继续固定旧版，不把维护责任交给自动同步。

切换按一个确定提交执行。此后原仓对应目录停止接独立修改，可发布从 sleuth 导出的独立包，或保留迁移指引；仍需兼容独立使用时，共用分析实现，分别提供入口文本。两边都需要独立发布节奏时，也可把分析器单独成库，sleuth 继续按本节固定版本消费。

### 9.6 模拟一次上游更新（验收用）

这套流程要有一次演练，否则第一次真遇到上游更新才发现哪一步断。演练只在仓库外的临时副本里做，不提交。

对副本做三处改动，跑 9.3 的六步：

1. **改一行，落在我们没覆盖的文件**：改 `cluster-analysis/references/msprof_cli.md` 的一句话。预期进「直接替换」，因为该文件没有覆盖文件。
2. **改一行，落在我们覆盖过的位置**：改 `prof-compare/scripts/run_compare.py` 里那段自动安装。预期进「人工」——三方比较发现同段冲突，不能静默按旧覆盖文件套上去。
3. **改一个文件名**：把 `cluster-analysis/vendor/prof-compare/SKILL.md` 改名。预期进「人工」——映射表报「源路径消失、新增未归属文件」，而不是当新文件忽略。

判定：三处分别落进这三档，且没有任何一处静默通过。任一处静默变成「直接替换」即失败，回到映射表与覆盖文件清单查漏。演练通过才允许对真实上游提交发起第一次同步。
