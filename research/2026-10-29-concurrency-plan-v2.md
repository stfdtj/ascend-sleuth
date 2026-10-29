# 并发知识入库 V2：最终架构与实施提案

状态：**评审稿**，供团队评审拍板。
取代 [上一版统一方案](2026-10-28-unified-plan.md) 作为决策文档；旧文保留，不删除。
证据基线：[`../diagnostics/concurrency-validation/`](../diagnostics/concurrency-validation/README.md)（下称“验证报告”）。

本文把已验证事实、实验复现、原型结论、待验证假设分开写。凡标“待验证”的，不得在评审时当作承诺。

---

## 1. 问题与目标

### 1.1 问题

多个工程师在各自 clone 中诊断、沉淀、groom、提 PR。当前系统在单人和单 PR 路径上工作正常
（一次完整 E2E 全部检查通过，合入后 main 的生成物被正确重建），但并发时会出现**静默**失败：

- 同一 inbox 的两个 writer 覆盖同名草稿（10/10 轮只剩一方，文件仍是合法 YAML）；
- 两个 clone 对同一问题给出不同 Case ID，两个 PR 都干净合入，所有检查通过；
- 同路径冲突解冲突时取一边，另一边内容消失，索引重建后所有门仍绿；
- 同一 Case 的两处不相邻字段各自修改，Git 干净合并出语义矛盾的 Case；
- 先合入的 PR 使另一个 PR 的“新增”判断过期，但没有重新判断的机制；
- 改 Case ID 后引用/使用记录报错，回放夹具只警告，trace/provenance 完全不检查；
- 两台机器生成同期号指标文件，解冲突只留一份，没有检查报告“少了一期读数”。

验证报告把这些归纳为 E1–E10，并新增 E11–E14（见 §4）。**当前规则集也没有强制力**：PR 必需，
但 0 个批准、没有必需检查、没有“分支必须最新”。这不是代码缺陷，而是治理事实。

### 1.2 目标（按优先级）

1. **本地不丢**：草稿不覆盖、半套/损坏材料不被消费。
2. **升格前发现**：共享来源、同 ID、同路径、同类/跨类、证据复用、条件冲突的材料进入复核。
3. **合入前重新判断**：对**实际要合入的集成状态**复核，过期决定不能继续用。
4. **不能绕过**：必需检查、非作者批准、分支最新（merge queue 可选）真正生效。
5. **可追溯、可恢复**：来源、字段出处、被舍弃内容、Case 谱系、验证事件可查；不能查的就如实标“不可查”。
6. **引用/夹具/使用记录/指标**随 ID 与合并保持一致；同一事件不被算两次。

### 1.3 非目标（明确不做）

- 不做全局草稿服务器、分布式锁、实时同步、跨机事务；Git 是唯一共享状态。
- 不做“诊断时全局一致”：允许各 clone 看到不同版本的 Knowledge，但必须记录 `kb_rev` 并提示落后。
- 不让 CI/LLM 自动判定“同一根因”；不自动合并、不自动裁决语义。
- 不把向量检索或 LLM 相似度做成合并门。
- 不承诺候选召回完整；不承诺 CI 验证不可访问的本地文件。
- 不重写历史使用记录；不把两个 ID 的计数直接相加。
- 不修改生产知识、Case、Reference、Trace、Metrics（本任务只交付设计）。

### 1.4 相对 V1 的实质变化

1. **Draft 身份**从 `日期-来源-序号` / `(deployment, draft_id)` 改为 **UUID**；deployment 只用于
   provenance，不参与唯一性。
2. **B 不再追求“六轴全库比较”**：生成与展示分离；mandatory/high/low 三层；mandatory 不设上限，
   high 超预算要显式 ack，low 只报数量。跨 namespace 只在有理由时查。
3. **B 与 C 合并为一个比较器**（`case_match.py`）：C 不另写一套重复检测。
4. **C 的保证改为平台事实**：required `kb-required`（聚合）、1 非作者批准、up-to-date（merge queue 可选）、
   bot bypass；不再把“报告里写了 SHA”当成保护。
5. **新增 O 同步层**：把 pull / 搜 PR / 诊断前更新做成 O1/O2，但明确它只降低“没看见”的概率，
   不替代 C。
6. **Provenance 改为“committed manifest + 可选脱敏材料 + 如实标注 local-only”**，取消对不可访问
   本地文件的假校验。
7. **计数不迁移**：历史使用记录保留；事故级指标按 `incident_key` 另算，不把两个 ID 相加。
8. **E10–E14 进入实施表**：E11/E12 与平台强制列为 P0，E10/reader/心跳按优先级排入。

---

## 2. 现有工作流与已确认的失效点

### 2.1 实际执行路径（已核实）

`诊断`（agent 对话 + `traces/<session>.yaml`）→ `沉淀`（`to-postmortem`/`issue-ingest` 写
`postmortems/inbox/<case-id>.md` + `<case-id>.case.yaml`）→ `groom`（按 `(ns × category)` 视图预分诊，
`verify_case_draft.py --gate`，升格到 `knowledge/`）→ `PR`（源文件 only，`generated-guard` 挡生成物）→
`CI`（kb-checks 14 个 job）→ `合入` → `rebuild-generated` 在 main 重建并提交生成物。

关键实现点：

| 能力 | 位置 | 状态 |
|---|---|---|
| inbox 锚主检出、跨 worktree 共享 | `scripts/shared_dir.py`、`scripts/exec_log_path.py` | 已实现 |
| 平铺草稿、无完成标记 | `skills/to-postmortem/SKILL.md`、`postmortems/inbox/README.md` | 已实现 |
| 草稿唯一结构门 | `scripts/verify_case_draft.py` | 已实现 |
| 按格预分诊 | `skills/knowledge-groom/SKILL.md` | 已实现（判断） |
| 全库查重 / 合入复核 | 无 | **不存在** |
| 生成物主干重建 | `.github/workflows/rebuild-generated.yml` | 已实现，API 观测到成功运行 |
| 规则集强制 | GitHub ruleset `main-protection` | PR 必需，但 0 批准、无必需检查、无最新要求 |
| Provenance | 无 | **不存在** |

### 2.2 已复现的失效（详见验证报告 02）

- **E1** 同名草稿并发：10/10 轮一方静默消失；3/3 轮流式写产生混合内容；崩溃留半套不被识别。
- **E2/E3** 两个 clone 同问题不同 ID：两种合入顺序都 0 冲突、全绿、两条都进索引。
- **E4/E5** 同路径冲突：`add/add`；取一边后另一边根因消失，全部检查绿。
- **E6** 不相邻字段各自修改：干净合并，`compat` 与 `diagnosis` 互相矛盾，全绿。
- **E7** 生成物：当前部署已由主干 job 重建（6 次运行，已查看的运行均成功）；但无 job 的部署会 main
  索引红、无 CI 信号。
- **E8** 过期判断：B 的 clone 没有 A 的 Case；无 recheck；合入成功。
- **E9** 改 ID：引用/使用记录硬报错，夹具仅警告，trace/provenance 不检查；归档重复 Case 保留两份计数且
  `verify_entry_activity` 绿。
- **E10** 同期号快照：两台机器都选了同期号（同一周的同一天），内容不同；解冲突留一份后无检查。

### 2.3 新增缺陷（详见验证报告 02 §9）

- **E11** 全数字短 SHA 被 YAML 读成整数，`entry_activity.aggregate` 的 `sorted(checkouts)` 抛
  `TypeError`；该生成器在 post-merge job 里，导致 main 生成物停更。
- **E12** `metrics_snapshot.py` 的输出被 `verify_metrics.py --check` 判红（1 个字段超白名单、6 个指标
  缺强度档）；按文档跑周快照会红。
- **E13** 规则集弱于文档假设（见 §2.1 表）。
- **E14** inbox 没有 reader contract：半套通过唯一草稿检查；混合内容可能仍是合法 YAML。

### 2.4 实验边界

- 所有实验在一次性 clone 中、用合成内容完成；未改动真实分支/草稿/Case/Trace/Metrics。
- GitHub 行为只通过公开 API 读取，没有创建 PR、没有改 ruleset、没有触发 CI。
- 原型代码不是产品实现；B 的 D1–D11 数字来自合成夹具，不能当作生产准确率。

---

## 3. V2 总体架构

```
                  ┌──────────────────────────────┐
                  │  O 同步层（新增，非强制）      │
                  │  kb_sync：诊断/PR 前对齐 main  │
                  │  pr_radar：看开放 PR 的改动    │
                  └──────────────┬───────────────┘
                                 │
诊断 ── trace ──► A 草稿队列 ──► B 候选与决定 ──► PR ──► C 合入复核 ──► 合并队列 ──► main
  (记录 kb_rev)   (UUID/目录/   (同一比较器；    (decision    (同一比较器；   (必需检查)   │
                   DONE/严格     tiers；人决定)   file)        field diff)                │
                   reader)                                                              ▼
                                                                         post-merge 重建 + 心跳
                                                                                   │
                                                                         Provenance / 引用 / 指标
```

六个不变量：

1. **一个比较器**：`case_match.py` 是唯一“两个知识单元怎么比”的实现；B 与 C 只是输入不同。
2. **机器提名，人决定**：机器给候选、轴、结构矛盾；`new/variant/covered/deferred/separate` 由人写进
   机器可读的 decision 文件。
3. **Git 是唯一共享状态**：Draft 本地、Trace 本地；进入评审的内容必须进 Git。
4. **失败要可见**：高优先级未决不能静默放过；低优先级可以只报数量，但必须写“未审核”。
5. **不能验证的就不假装验证**：本地文件只标 `local-only`，CI 不校验其字节。
6. **平台强制才算保证**：报告、脚本、清单本身不是门；必需检查 + 批准 + 最新（merge queue 可选）才是。

### 3.1 组件与落点

| 组件 | 类型 | 落点 | 依赖 |
|---|---|---|---|
| `kb_sync.py` | 新脚本 | `scripts/` | git |
| `pr_radar.py` | 新脚本 | `scripts/` | git / GitHub API（可选） |
| `draft_queue.py` | 新脚本（reader + 路径） | `scripts/` | 无 |
| `inbox_put.py` | 新脚本（writer） | `scripts/` | `draft_queue.py` |
| `case_match.py` | 新模块（唯一比较器） | `scripts/` | `_lexical.py`、`build_index.sig_literals` |
| `find_duplicates.py` | 新脚本（B 生成/展示） | `scripts/` | `case_match.py`、`draft_queue.py`、`pr_radar.py`（可选） |
| `merge_recheck.py` | 新脚本（C） | `scripts/` | `case_match.py`、`case_diff.py`、git |
| `case_diff.py` | 新模块（同 Case 字段 diff） | `scripts/` | 无 |
| `verify_decisions.py` | 新检查 | `scripts/` | decision 文件、`merge_recheck` 输出 |
| `verify_provenance.py` | 新检查 | `scripts/` | provenance manifest |
| `rename_case.py` | 新工具 | `scripts/` | refs/fixtures/usage/provenance |
| `kb-required` job | CI 聚合门 | `.github/workflows/kb-checks.yml` | 所有 job 的 `needs` |
| `deployment_id.py` | 新脚本（生成/校验 deployment.id） | `scripts/` | 无 |
| `deployment.id` | 配置字段 | `deployment.yaml` | 无 |
| 面板 reader | 两处 | `dsh-plugins/ascend-panel/panel-host.js`、`dsh-plugins/dsh-sleuth-panels/lib/index.js` | 同一契约 + 契约测试 |

---

## 4. O 同步层：pull / 搜 PR / 诊断前更新，分层采纳

### 4.1 结论

“PR 前 `git pull`、groom 时搜开放 PR、诊断前更新知识库”这三条**方向正确，必须做**；但它们
**不能替代 Checkpoint C 的强制**：

- `git pull` 只把本地副本更新到某一时刻；之后 main 再前进，本地复核又过期。没有“分支必须最新”
  （或 merge queue），平台仍允许合入。
- 搜开放 PR 能显著提前发现冲突（尤其是还没合入的 A），但依赖网络/权限，且 PR 可能在你检查后更新。
- 诊断前更新知识库改善召回，但诊断读的是本地检出；更新必须记录版本，且不能在诊断中途变。
- 三条都不解决本地草稿覆盖（草稿不在 Git 里）。

因此 V2 把它做成**同步层 O1/O2**：低成本、可脚本化、覆盖“早发现”；强制仍由 C 的 required check +
up-to-date 负责。

### 4.2 O1 `scripts/kb_sync.py`

用途：让“我这份 Knowledge 是哪一版”变成可执行事实，而不是记忆。

```bash
python3 scripts/kb_sync.py --check          # fetch + 打印 behind/ahead/脏工作区 + kb_rev
python3 scripts/kb_sync.py --require-fresh  # behind>0 或脏工作区 → 退出码 2（groom/PR 前用）
python3 scripts/kb_sync.py --ff-only        # 仅干净工作区、无本地提交时快进当前分支
```

行为：

1. `git fetch --prune origin`；比较 `HEAD` 与 `origin/main`，报告 `behind/ahead` 与 `kb_rev`（短 SHA）。
2. `--require-fresh`：`behind > 0`、工作区脏、或 fetch 失败 → 非零并打印修复命令。**用于 groom 与
   PR 前**，不用于诊断中。
3. `--ff-only`：只在干净、无本地未推送提交、当前分支可快进时执行；否则拒绝，不做 merge/rebase。
4. 诊断开始时：`kb_sync.py --check`，把 `kb_rev` 与 `kb_stale: true|false` 写进 trace（`kb_rev` 字段已存在，
   `kb_stale` 是新增可选字段）。**不**在诊断中途自动改知识库：一次诊断的候选与判断必须对同一版本可复现。
5. 诊断前“更新知识库”的推荐做法：会话开始、工作区干净时 `--ff-only`；否则先记录 `kb_rev` 并提示
   落后，不强行更新。

集成点：

- `skills/diagnose/SKILL.md` 第 1 步加一条：`kb_sync.py --check`，记录 `kb_rev`；
- `skills/knowledge-groom/SKILL.md` 第 1 步与 PR 前：`--require-fresh`；
- `docs/guide/git-workflow.md` 的“开工纪律”从 prose 改为命令；
- `skills/diagnose/references/diagnosis-trace.md` 增补 `kb_stale` 字段说明（可选字段，旧 trace 不追溯）。

### 4.3 O2 `scripts/pr_radar.py`

用途：在 groom 时看到**尚未合入**的开放 PR 所引入的 Case，提前发现 A/B 撞车。

已验证：`git ls-remote origin 'refs/pull/*/head'` 能列出 **378** 个 PR ref；在一次性仓库中用
`git fetch --depth 1 origin refs/pull/378/head:refs/remotes/pr/378` 成功取到该 PR 的树（未改动真实仓库）。

两级实现：

1. **有 GitHub API token（CI 或本地 `GH_TOKEN`）**：列 open PR 的 `number/head.sha/base.ref/updated_at`，
   只取目标分支为 `main` 的 PR；缓存 `(number, sha)` 到主检出的 gitignored 状态文件；只 fetch sha 变化的
   PR head（`--depth 1`），上限 50。
2. **无 token（普通本地）**：`git ls-remote origin 'refs/pull/*/head'`，用 PR 编号降序取最近 N=30 个；
   跳过已是 `origin/main` 祖先的 head（已合入）；其余标记 “unmerged (可能已关闭)”，不假装知道 open/closed。
   首次运行可只扫与本次 draft 的 namespace/关键词相关的 PR？做不到——ref 名不含路径；因此只做最近 N 个。

输出：每个 PR 的 changed `knowledge/**/*.yaml` 解析成 Case 记录，交给 B 的同一比较器；报告里单列
“可能由开放 PR 引入的知识（PR #n）”。**它不是门**：CI 的 C 仍以 `origin/main` 为准；radar 只是提前量。

限制（写进文档）：

- 378 个 ref 全量 fetch 成本高；必须按 sha 增量、限 N、`--depth 1`；
- 无 API 时无法区分 open/closed；可能显示已关闭 PR；
- 网络失败不阻塞 groom（降级为“未检查开放 PR”，并在摘要写明）；
- 不做“PR 间实时一致”，只做检查时快照。

### 4.4 为什么不是“只要 pull + 搜 PR”

| 做法 | 能解决 | 不能解决 |
|---|---|---|
| PR 前 pull | 本地判断基于较新 main | pull 后的新合入；无强制时仍可合旧分支 |
| 搜开放 PR | 提前看到 A 的 Case | A 之后又更新；无 token/网络；已关闭 PR 噪声 |
| 诊断前更新 | 候选更新、减少 stale 命中 | 草稿覆盖；groom 判断过期；合入顺序 |
| 三者相加 | 大幅降低“完全没看见”的概率 | **不能提供合入时的保证**——这正是 C 的职责 |

---

## 5. Checkpoint A：草稿身份与完整性

### 5.1 身份模型（五件事分开）

| 身份 | 取值 | 生命周期 | 用途 | 是否要求全局唯一 |
|---|---|---|---|---|
| Draft ID | `uuid4`（36 字符） | 一次沉淀一个，永不复用 | 目录名、provenance 引用、reader | **是**（UUID 即可） |
| Diagnosis session | 现有 `traces/<session>.yaml` 的 session_id | 一次诊断 | 追到现场；可多个 session 指向同一事故 | 否（本机唯一即可） |
| Deployment ID | `deployment.yaml` 的 `deployment.id`（uuid4，首次部署生成） | 部署/克隆 | Provenance 分组、面板、诊断；**不参与唯一性** | 否（同名部署应各自生成） |
| Case ID | groom 确认 | 知识库生命周期 | 检索、引用、使用记录 | 是（现有 `build_index` 保证） |
| Revision ID | 新 draft 的 uuid + `supersedes` | 每次 reopen 一个 | 修正已完成草稿 | 是（新 UUID） |

**决定：Draft ID 用随机 UUID，不用 `deployment + draft_id`。** 理由：UUID 在并发、独立 clone、
复制仓库、目录改名下都不冲突；deployment 标签是给人看的，不是身份。Deployment ID 只用于
provenance/诊断（“这条知识来自哪台机器/哪个部署”），缺失时写 `unknown`，不影响正确性。

Deployment ID 由 `scripts/deployment_id.py --init` 首次生成并写进 `deployment.yaml`（`doctor.py`
在缺失/重复风险时提示）；它是随机 UUID，不复用目录名或仓库名。它不参与 Draft/Case 唯一性，因此
复制 `deployment.yaml` 造成的重复只影响“来源统计”，不会造成身份冲突；文档要求副本重新生成。

### 5.2 目录与文件

```
postmortems/inbox/<uuid>/
  case.yaml          # 与正式 case 同形（cases: 列表）
  postmortem.md      # 人读复盘；可为指针（源已是结构化文档时）
  sources.yaml       # 来源/条件/验证/字段摘要（见 §8）
  DONE               # 原子发布；最后写
```

`sources.yaml`（最小字段）：

```yaml
draft_id: 6f1c...            # 必须等于目录名
created_at: "<ISO-8601>"
source:
  kind: diagnosis            # diagnosis | issue | manual
  deployment_id: 6a2f...     # 可选；缺失写 unknown
  session: "<session-id>"   # 主 session；可为空
sessions: ["<session-id>"]  # 可多个
conditions:
  workload_type: inference   # training | inference | unknown
  framework: vllm-ascend
  versions: {vllm-ascend: 0.22.0}
  platform: A2-310P
  stage: 启动
verification:
  - event_id: "feedback:<session-id>:1"   # 见 §8.4；没有就写 none
    kind: feedback
semantic_summary:
  root_cause: ...
  fix: ...
  signature: ...
supersedes: null             # 修正时填旧 draft uuid
```

- **Draft 内的 Case ID 是建议值**，不是最终身份：`case.yaml` 里仍需一个 `id`（`verify_case_draft`/
  build 工具要用），groom 升格时确认或改写；改写只发生在未入库的 draft 内，成本低。最终 Case ID 由
  groom 定，Draft 身份始终是 UUID。

### 5.3 写入协议（`inbox_put.py`）
```bash
python3 scripts/inbox_put.py new --source diag --session <sid>   # mkdir 独占 + 打印绝对路径
python3 scripts/inbox_put.py finish <dir>                        # 校验三文件 + 哈希 + 原子 DONE
python3 scripts/inbox_put.py list [--json]                       # 统一 reader
python3 scripts/inbox_put.py reopen <dir>                        # 标记 SUPERSEDED，建新 draft
python3 scripts/inbox_put.py abort <dir> --force                 # 只删未完成
```

规则：

1. `new`：`os.mkdir(postmortems/inbox/<uuid>)` 独占创建；UUID 冲突概率可忽略，遇到 `FileExistsError`
   重新生成（最多 3 次，仍失败则报错）。**不做“先查再写”**。
2. `finish`：三文件必须存在；`sources.yaml.draft_id == 目录名`；两个 YAML 可解析；`case.yaml` 顶层有
   非空 `cases`；计算三文件 sha256；写 `DONE.tmp`（`fsync`）→ `os.replace` 成 `DONE`。
3. `DONE` 已存在时 `finish` **拒绝**；要改内容必须 `reopen`（见 5.5）。
4. `abort --force` 只删无 `DONE` 的目录；有 `DONE` 的拒绝。
5. 不做自动清理；groom 每周报告 `incomplete/corrupt` 数量与最老年龄。

### 5.4 一个读者契约（所有消费者共用）

`scripts/draft_queue.py list --json` 返回：

| state | 判定 | 可消费 | 报告 |
|---|---|---|---|
| `complete` | DONE 可解析；含 `completed_at`；`files` 恰为三文件；哈希全匹配；`draft_id` 无冲突 | 是 | 正常 |
| `incomplete` | 无 DONE（可以有 `DONE.tmp`） | 否 | groom 摘要列出数量/年龄 |
| `corrupt` | DONE 解析失败、files 缺失/多余、哈希不符、draft_id 不一致、YAML 解析失败 | 否 | 必须报告，不静默 |
| `superseded` | 存在 `SUPERSEDED` 标记（reopen 产生） | 否 | 指向新 draft || `legacy_flat` | `<id>.case.yaml` + `<id>.md`，无 sources/DONE | 是（带 `legacy: true` 警告） | 不迁移，长期兼容 |

reader 先看 `SUPERSEDED`/`SUPERSEDED_BY`，有标记即 `superseded`，再校验 DONE；`DONE` 与
`SUPERSEDED` 同时存在时以后者为准。

消费者：

- `to-postmortem` / `issue-ingest`：只通过 `inbox_put.py new/finish` 写；
- `knowledge-groom`：只消费 `complete` 与 `legacy_flat`；`incomplete/corrupt` 只报告；
- `find_duplicates`：只把 `complete` 与 `legacy_flat` 作为输入；**不得**读未完成目录；
- 两个面板：读同一契约；用 `tests/fixtures/inbox/*` 的固定样本做契约测试（见 §11.3）；
- `sediment_batch.py`：`--inbox-path` 接受目录；回写 `submitted` 时记录 dir path；
- `docs`/README：只承诺 reader 定义的四种可消费状态。

### 5.5 完成后的修改 / 修订

- 已完成草稿视为**不可变**。任何字节变化 → reader `corrupt`；groom 不消费。
- 需要修正：`inbox_put.py reopen <old>`：
  1. 在旧目录写 `SUPERSEDED`（含 `superseded_by: <new uuid>`、时间、原因）；
  2. 新目录复制三文件，生成新 UUID，`sources.yaml.supersedes: <old>`；
  3. 旧目录保留（可恢复），reader 报 `superseded`；
  4. provenance 记录 `revises`。
- 为什么不做 `--refinish`：验证报告已证明重盖章会让“DONE+哈希匹配”失去意义；reopen 把修改变成新事件，
  可审计、可恢复。

### 5.6 崩溃矩阵与恢复

| 崩溃点 | 结果 | 消费？ | 恢复 |
|---|---|---|---|
| mkdir 前 | 无目录 | — | 重跑 |
| mkdir 后、写文件前 | 空目录，无 DONE | 否 | 继续写或 abort |
| 写文件中 | 部分文件，无 DONE | 否 | 继续/abort |
| 写 DONE 中 | `DONE.tmp` 或半截 DONE | 否 | 删除 tmp；重跑 finish |
| DONE 后 | complete | 是 | 正常 |
| DONE 后文件被改 | corrupt | 否 | reopen |
| 两个 writer 同名 | UUID 不同，不冲突 | 各自 complete | 正常 |
| 进程崩溃 + 重跑 | 新 UUID，不会覆盖旧的 | 旧 incomplete 留着 | groom 报告清理 |

### 5.7 旧平铺草稿

- 永久兼容读取；不做一次性批量转换（旧数量少，转换收益低于兼容成本）。
- 旧平铺草稿没有 provenance/conditions，B 把它标 `legacy: true`，轴 `source/conditions/evidence` 为
  `unknown`，不假装完整。
- 新产出只写目录；旧草稿被消费后自然减少。
- `.gitignore` 已覆盖 `postmortems/inbox/*`，目录也在内，无需改。

### 5.8 失败/风险

- 绕过工具直接写文件仍会回到旧行为；文档必须写明覆盖范围，groom 报告“非工具写入”的迹象
  （如无 `sources.yaml` 的目录）。
- 面板两份实现可能漂移：用同一 fixture 契约测试；长期合并为一份（P2）。
- UUID 目录可读性差：报告/面板显示 `created_at + title + session`，不显示裸 UUID 作为主标识。
- 复制仓库：旧草稿的 UUID 不变（正确：同一材料被复制），但 deployment_id 可能相同；provenance 用
  UUID 不冲突；deployment 只用于说明来源，不做唯一键。

### 5.9 验收

- 8 个进程同时 `new` → 8 个不同目录；
- 三种崩溃点 → `incomplete/corrupt`，`list` 可解释，`finish` 非零；
- DONE 后改一字节 → `corrupt`；
- `reopen` → 旧 `superseded`、新 complete，provenance 记 `revises`；
- 两个 clone 各自 `new` → 目录不同（UUID），不冲突；
- 旧平铺仍被 groom 读取；
- 两个面板对同一 fixture 显示一致（契约测试）。

---

## 6. Checkpoint B：候选生成与展示

### 6.1 原则

- **生成**与**展示**分开：先生成所有超过低阈值的候选，再按 tier/预算决定给 reviewer 看什么。
- **机器只提名**：给信号、轴、矛盾提示；不给“重复/不重复”的结论。
- **mandatory 不能藏**：身份级候选（共享来源/同 ID/同路径/同验证事件/强判别式）永远展示，且没有
  决定就不能升格。
- **high 不能静默**：核心候选超过展示预算时，必须显式 ack（记录隐藏数量、原因、人），否则阻止升格。
- **low 只报数量**：明确写“未审核”，不算作已复核。
- **跨类/跨命名空间有理由才查**：不做无差别全库相似度。

### 6.2 唯一比较器 `scripts/case_match.py`

从现有实现抽出的纯函数：

- token：`scripts/_lexical.tokens_of`（已有）与 `scripts/build_index.sig_literals`（已有）；
- 字段：id/title/tags/symptoms/root_cause/fix/quickly_check（command/expected/selector）/compat/platforms/
  upstream/source_session/validation_record/source_ref；
- 比较：normalized expected、command 相似、版本区间（解析 `>=`/`<`/`==`/裸版本；无法解析→unknown）、
  platform（前缀/精确；无层级就写 unknown）、upstream 元组、event/session 集合、强关键词（错误码、
  算子名、`*.py` 源码位置）；
- **权威字段**：`case.yaml` 的 `compat/platforms/root_cause/fix` 是知识本体；`sources.yaml` 的
  `conditions/semantic_summary` 只用于匹配与来源说明。两者不一致时，`case_match` 返回
  `inconsistent: true` 并在报告里标出，不自动选一个（这条是 V1 验证报告指出的“两个真相源”问题的
  修复）；
- 输出：`{signals, scores, axes, hints}`，不读 Git、不写文件。

`build_index.py` 改为从 `case_match` 取 `sig_literals`/token（行为不变，加回归测试），避免两套 tokenizer。

### 6.3 信号与 tier

**Tier 1 — mandatory（必须决定，不设上限）**

- 共享 upstream：`repo + issue` 或 `repo + pr` 相同；
- 同 Case ID；
- 同路径；**主要适用于 C 与 changed-from 输入**：组目录 draft 的路径是
  `postmortems/inbox/<uuid>/case.yaml`，legacy flat 是 `postmortems/inbox/<id>.case.yaml`，都不是知识
  路径；这两类 draft 的“同路径”由同 Case ID 覆盖（文件名=ID），不要用 inbox 路径去比；
- 同 verification event id（看 §8.4；event id 来自 provenance 的 `evidence[].event_id`；**没有 event id
  时不触发，不用 `source_session` 冒充**；旧 Case 没有 provenance → `unknown`）；
- **强判别式**：normalized full expected 相同 **且** 共享至少一个 `sig_literals`（长度 ≥6）或
  command token 重合 ≥0.6。单纯 `regex:^[1-9]` 这类通用期望不算。

**Tier 2 — high（必须展示；超过预算要 ack）**

- 同分类同格：症状/标题 token 重合 ≥0.28，且（root/fix 重合 ≥0.5 或共享强关键词）；
- 同 namespace 跨分类：重合 ≥0.20，且（root/fix ≥0.5 或条件有交集或共享强关键词）；
- **跨命名空间（有理由）**：`common/` 永远比；training↔inference 仅在下列之一成立时比：
  draft 的 `workload_type` 为 unknown/缺失（此时 `_ns` 按 wildcard 处理，与所有 namespace 的 high
  规则比较，但仍需满足 high 的词法/字段条件，不做全库无差别扫描）、draft framework 为 common/跨框架、
  共享强关键词/upstream/event、root/fix 重合 ≥0.5、条件有交集；
- root 重合 ≥0.6 且两侧 token ≥4；fix 重合 ≥0.6 且两侧 token ≥4；
- 条件有交集且症状重合 ≥0.30；
- 同 session（证据复用候选；非 mandatory，因为一次事故可含多个独立问题）；
- 结构矛盾提示（见 6.4）**且**该对已过相关性下限（score ≥0.20 或上述任一信号）；提示本身不升级。

**Tier 3 — low（只报数量，不要求决定）**

- 同格/跨格纯词法 ≥0.30、共享弱关键词、title 相似等；显示 top 2/draft + 全局 10，其余只报数。

### 6.4 结构矛盾提示（机器只标“需要读”）

1. 同期望值、修复词重合低 → `same-check-two-fixes`；
2. `fix_on_mismatch` 提到的版本落在受影响区间 → `affected-version-vs-fix-version`；**必须先过相关性
   下限**，否则大量无关 Case 会因 “0.23.0” 命中而刷屏（V2 设计实验已观察到这个假阳性）；
3. 同 session/同 event 被两处引用 → `same-evidence`；
4. 同 upstream、root 重合低 → `same-issue-different-root-cause`；
5. 症状重合高、条件无交集 → `same-symptom-disjoint-ranges`。

提示不写“重复”，只写“这里需要读”。

### 6.5 排序、展示、溢出

排序（确定性，不含权重调参空间之外的黑盒）：

1. mandatory 全部（按：同 upstream/同 ID/同路径/同 event/强判别式）；
2. high：核心条件优先（root/fix 重合 → 跨分类 → 条件交集 → 同 session → 仅矛盾提示）；
3. low：先按是否带矛盾提示，再按 score；**low 不进入决定要求**。

预算（默认，可配置）：

- mandatory：全部展示；没有上限。若 >30，提示“本次 groom 建议拆批”，但**不隐藏**。
- high：全部展示，最多 30 对；>30 → 每 draft 生成 `overflow` 项，**阻止该 draft 升格**，直到 reviewer
  二选一：`--show-all-high` 复核，或写 `ack_overflow: {hidden_count, reason, reviewer}`。ack 明确记录
  “这些没看”，不是“已审核”。
- low：每 draft 最多 2 对 + 全局 10 对；其余只报 `hidden_low` 数量；不进决定文件。

去重：同一 `(case_id, draft_id)` 只出现一次；多个 draft 命中同一 Case 时合并成一行列出所有 draft。
报告按“draft 分组 → 组内 mandatory/high/low”排列，跨 draft 的同一 Case 只出现一次但标出全部 draft；
每行给 pair_id、tier、信号、两段根因/修复摘录、判别式、条件、证据、矛盾提示、待填决定。

D1–D11 验收（V2 设计实验，合成夹具，**非生产准确率**）：

| 目标 | 结果 |
|---|---|
| D1 跨分类同根因 | high，已展示 |
| D2 改述（root/fix 文本相同） | high，已展示（旧版漏；V2 加 root/fix 信号后可见） |
| D3 同判别式不同根因 | mandatory，已展示 + `same-check-two-fixes` |
| D4/D5 同 upstream 两问题 | mandatory（draft-draft），已展示 + `same-issue-different-root-cause` |
| D6 同修复不同版本 | high，已展示 + `same-symptom-disjoint-ranges` |
| D7 条件重叠 | high，已展示 |
| D8 矛盾修复、条件不相交 | mandatory，已展示 + 两条提示 |
| D9 同验证事件 | high，已展示（event id 机制后升为 mandatory；当前夹具只有 session） |
| D10 同诊断不同 session | high，已展示 |
| D11 无关对照 | 不生成、不展示 |

计数（11 drafts × 173 cases）：生成 300 对；mandatory 4（draft-vs-library 计数；D4/D5 的 draft-draft
对另计，见上表）；high 17；low 279；**展示 31**；hidden high 0；hidden low 269。reviewer 看到 21 个核心 +
10 个低优先 watchlist ≈ 30–45 分钟。
**注意**：合成夹具的 root/fix 文本高度相同，实际库的 root 重合会低很多；这个数字只证明机制，
不证明生产环境的召回/工作量。实现时必须用真实标注样本重跑。

### 6.6 决定文件（机器可读，进 Git）

PR 模板加一个简短的“查重与决定”区块，引用 decision 文件；**机器门只读文件，不读 PR prose**
（`verify_pr_body` 只查标题，不能证明判断）。

`postmortems/decisions/<case_id>.yaml`（每个新/修改 Case 一份）：

```yaml
case_id: VLLM-ASC-12345
decision: new            # new | variant | covered | deferred | separate
main_sha: <扫描时的 origin/main>
head_sha: <扫描时的 HEAD>
tool_version: plan-v2
pairs:
  - pair_id: <sha1(draft_uuid + ":" + case_id)>   # 稳定；不随阈值/信号变化
    other: VLLM-ASC-10097
    tier: mandatory | high
    signals: [shared-upstream]
    decision: separate   # new | variant | covered | deferred | separate
    note: "同一 issue，不同根因；保留两条"
overflow:
  hidden_high: 0
  ack: null             # 或 {hidden_count, reason, reviewer}
```

检查（`verify_decisions.py`）：

- 每个 PR 新增/修改的 Case 都有 decision；**旧 Case 首次被修改时也新建一份 decision**（不要求补历史
  provenance）；
- **以 `merge_recheck` 在合入时重算的 mandatory/已展示 high 集合为准**，decision 里这些 pair_id 必须
  全部出现（不是拿 groom 当时的旧集合比对）；新出现的 mandatory/high → 退出 2，先 `--refresh-decision`
  补决定；
- 若 `overflow.hidden_high > 0`，必须有 ack；
- `main_sha` 必须是当前 `origin/main` 的祖先且与本次复核的 base 一致（C 检查 freshness）；
- 不校验 decision 的内容对不对（人审）。

**未升格的材料也要有去向。** `covered/deferred/archived` 的 complete draft 没有 Case ID，decision 写
`postmortems/decisions/drafts/<draft_uuid>.yaml`（`case_id: null`，`materials: [draft_uuid]`，
`decision: covered|deferred|archived`）。`verify_decisions` 检查**本次 PR 提交的**每个 complete draft /
每个被 PR 引用的 material 都有决定；它无法知道一个从未提交、也从未出现在任何 PR 里的本地草稿——这是
reader/流程的覆盖边界，groom 摘要必须列出本轮消费的 draft 数与去向，CI 只能校验已提交的部分。

### 6.7 B 与 C 的关系

- **同一个 `case_match`**：B 的输入是 `draft + (main library + open PR heads)`；C 的输入是
  `PR changed cases + latest main (+ open PR heads，可选)`。
- C 不复写 B 的候选逻辑；`merge_recheck.py` 直接调用 `find_duplicates` 的生成函数，传入不同输入。
- 决定文件在 groom 生成，C 在合入前刷新；两者引用同一 `pair_id` 与同一个文件。

### 6.8 不保证

- 语义完全等价但用词完全不同、且 root/fix 也改写的重复，可能漏；必须保留“人判断”与抽样审计。
- 词法相似不是语义等价；不自动合并。
- 跨命名空间只查“有理由”的子集；未查的写 unknown，不写“无重复”。

---

## 7. Checkpoint C：合入时一致性、强制与人工判断

### 7.1 目标

让“合入的是被验证过的那份内容”成为平台事实，而不是 reviewer 的记忆。C 不判断语义；它保证：

1. 复核针对**实际集成状态**（最新 base + 本次 head/merge candidate）；
2. mandatory/high 的决定文件齐全且未过期；
3. 同路径/同 ID/同一 Case 的字段冲突被看见；
4. 生成物、重命名、删除、悬挂引用被标出；
5. 必需检查、非作者批准、最新分支不可绕过。

### 7.2 `merge_recheck.py`

```bash
python3 scripts/merge_recheck.py --base origin/main --head HEAD --json
python3 scripts/merge_recheck.py --base origin/main --head HEAD --refresh-decision
python3 scripts/merge_recheck.py --verify-decision postmortems/decisions/<case>.yaml
```

CI 里不要依赖 `HEAD` 是 PR head：`pull_request` 默认 checkout 的是 test merge commit，`merge_group`
checkout 的是队列 commit。CI 调用时显式传 `--base "$BASE_SHA" --head "$HEAD_SHA"`（来自
`github.event.pull_request.base.sha/head.sha` 或 `github.event.merge_group.base_sha/head_sha`），
报告里的 `head` 必须是 PR head，而不是 GitHub 生成的 merge commit；`case_diff` 用两边 `git show`
读取，不依赖工作区 checkout 的分支名。

计算：

1. `git fetch origin main`（CI 已有）+ `git merge-base`；
2. 两侧 `diff --name-status -M`：新增/修改/删除/重命名；
3. Case ID 映射：新文件读 `cases[0].id`；删除读 base 版本；重命名保留 old→new；
4. 同 Case 两侧修改 → **字段级 diff**（`case_diff.py`）：`expected`/`fix`/`compat`/`platforms`/
   `symptoms`/`diagnosis` 等逐字段；重叠字段 → 必须填决定；不相交字段 → 允许但报告；
5. 同路径 add/add、同 ID 异路径、删除/重命名 + 对侧引用 → 冲突类；
6. head 侧变更 Case 与最新 main（以及可选 open PR）跑 B 的候选；
7. 生成物改动、decision 过期、`main_sha`/`head_sha` 不符 → 标出。

退出码（供 CI）：

| 码 | 含义 | 动作 |
|---|---|---|
| 0 | 无 mandatory/high 未决、无字段重叠冲突、决定新鲜 | 通过 |
| 1 | 决定过期（base/head 变了） | 重跑 `--refresh` 并提交 |
| 2 | mandatory/high 未决或 overflow 未 ack | 补决定/ack |
| 3 | 同 Case 重叠字段、同路径 add/add、删除/重命名+引用 | 人工解冲突，重跑 |
| 4 | PR 改了生成物 | 还原生成物，源文件重提 |

### 7.3 平台强制（必须与 C 同时上线）

当前 ruleset：PR 必需，`required_approving_review_count=0`、无 required status checks、无
up-to-date、无 merge queue。V2 要求：

1. **单一必需检查 `kb-required`**（聚合 job）：
   - 依赖 **`kb-checks.yml` 的全部 job**：`changes`、`generated-guard`、`index-freshness`、
     `case-structure`、`reference-validation`、`metrics-validation`、`proposal-audit`、`docs-index`、
     `holdout-integrity`、`eval-scorecard`、`unit-tests`、`panel-checks`、`skill-self-contained`、
     `arena-gate-rule`、**`merge-recheck`**；`pr-template` 目前是独立 workflow，**必须搬进
     `kb-checks.yml` 或复制其命令**才能被 `needs` 聚合（GitHub 的 `needs` 不能跨 workflow）。
   - 聚合 job 用 `if: always()` 运行（否则上游失败会把它自己也变成 skipped，required check 反而“通过”），
     读 `needs.*.result`：`failure/cancelled` → 红；`changes` 失败 → 红；**该跑却 `skipped`** → 红
     （每个 job 的 `if:` 条件与 `changes` 输出对齐，聚合 job 用同一组条件判断“应不应该跑”）。
   - 分支保护只 require `kb-required` 一个上下文；不要逐个 require 条件 job（skipped 会被算成功，
     且 workflow 级 `paths` 不命中时检查根本不出现）。P0-1 先聚合现有 job；P0-4 落地后再把
     `merge-recheck`（以及 `verify_decisions` 的检查）加进 `needs` 与 required。
   - **必须去掉 workflow 级 `paths:`**（`kb-checks.yml:15-20`），否则不命中路径的 PR 整条 workflow
     不启动，required check 永远不出现，PR 永久 pending。改为 job 级 `if:`（现有 `changes` 已经能算
     9 个面）；代价是 docs-only PR 也启动 workflow，但 job 跳过、成本很低。
   - P0 在 `pull_request` 事件上运行；若 P1 启用 merge queue，再在 `merge_group` 上加同样检查。
     `merge_group` 下 `GITHUB_BASE_REF` 可能为空，`merge_recheck` 用
     `github.event.merge_group.base_sha`（或 `origin/main`）计算 base，不能假定 PR 事件的变量存在。
2. **批准**：`required_approving_review_count: 1`，`dismiss_stale_reviews_on_push: true`，
   `require_last_push_approval: true`，`require_code_owner_review` 在 CODEOWNERS 落实后开启。
3. **最新/队列**：**P0 使用 “Require branches to be up to date before merging”**。这是最小、可在
   现有 ruleset 上验证的方案：base 前进后 PR 不能合，必须更新分支并重跑检查，decision 的
   `base_sha` 随之刷新。**merge queue 作为 P1 可选**：它能提高吞吐、减少排队，但 `merge_group` 的
   “集成 commit / PR head” 语义需要额外验证（见 §7.4），不作为 P0 的前提。
4. **机器人权限**：`DEPLOY_KEY` 对应 deploy key 只用于 `rebuild-generated`，加入 ruleset
   bypass；人类用户不加入 bypass。job 失败要红（已有），另加 main 心跳（§10.5）。
5. **CODEOWNERS**：`CODEOWNERS.example` 目前是占位；先落实 owner，再开 `require_code_owner_review`。
6. **分支保护测试**：必须在一个测试仓库/测试 PR 上验证：缺检查不能合、检查红不能合、
   分支落后不能合、批准后 push 使批准失效、bot 能推生成物、`changes` skipped 不会放行。

### 7.4 与 PR test merge / merge queue 的关系（重要）

- `pull_request` 的检查默认跑在 GitHub 生成的 **test merge commit**（`refs/pull/N/merge`）上。对
  `merge` 方法，tree 约等于“base + head”；对 squash/rebase，最终 commit 的父/历史不同，但 tree 来自
  PR head（rebase 时）或 head 的 squash（squash 时）。**只要 base 是最新的**，检查的 tree 与实际 land
  的 tree 一致；这就是 P0 选 “branches up to date” 的原因。
- `merge queue` 的 `merge_group` 事件检查的是队列实际要合的 commit；base 前进时队列会重建并重跑。
  但它引入两个需要验证的语义：① `merge_group.head_sha` 是队列 commit，不是 PR head；② 多个 PR 一起
  入队时，单个 PR 的 decision 如何与集成 tree 绑定。V2 不在 P0 引入；P1 若要开 queue，先在测试仓库
  验证，再决定是否用 `merge_group` 替换 `up-to-date`。
- **没有 up-to-date/queue**：检查后 base 再前进，C 的复核就过期；`dismiss_stale_reviews_on_push` 只
  处理 head 变化，不处理 base 变化。因此 P0 必须开 up-to-date，否则 C 不能承诺“对集成状态复核”。
- 结论：**P0 = required `kb-required` + 1 非作者批准 + up-to-date + bot bypass**。merge queue 是吞吐
  优化，不是正确性前提；什么时候加，取决于 P1 的验证。

### 7.5 六个场景的确定行为

| 场景 | B（groom） | C（合入） | 人的动作 |
|---|---|---|---|
| 1. A/B 同问题不同 ID | PR radar 看到 A 的 open PR → high/mandatory；否则 B 只看 main，可能判 new | 若 A 已合入，C 以最新 main 比 → mandatory/high，必须决定；若 A 未合入，C 可选 radar 但**不保证**（radar 非门） | 决定：分开/变体/覆盖/延后；写 decision |
| 2. A 先合入 | — | B 的 head 对 A 后的 main 重跑，决定文件 `main_sha` 变旧 → 退出 1 | 重跑 `--refresh`，补决定 |
| 3. B rebase/更新分支 | — | 新 head/base → 决定过期；`kb-required` 重跑 | 重新复核/刷新 |
| 4. B 的决定过期 | — | 退出 1/2；不通过 | 刷新并提交 |
| 5. 两分支改同一 Case 不同字段 | — | 字段 diff 不相交 → 报告；相交 → 退出 3，必须人工合并 | 按六轴/字段决定保留哪些 |
| 6. 干净合入但语义矛盾 | B 给提示 | C 不能判断；decision 必须有 `note`，reviewer 必须批准 | 人读双方；可能保留两段条件 |

### 7.6 CI 能强制 / 只能人判断

**能强制（机械）**：YAML/字段/ID/路径/引用/使用记录/夹具哈希/索引覆盖/生成物未改/decision 文件
齐全、pair_id 覆盖、`main_sha` 新鲜、同路径/同 ID/重叠字段的存在性、必需检查与批准、分支最新。

**只能人判断**：是否同一根因；两段修复能否合并；条件是否互斥；证据是否独立；合并后语义是否自洽；
reviewer 的决定是否正确。

**明确不保证**：required checks 不能保证语义正确；up-to-date 不能保证 reviewer 认真；decision 文件
不能证明人读过；候选不能保证召回。

### 7.7 失败与恢复

- decision 过期：重跑 `merge_recheck --refresh-decision`，提交更新；旧决定保留在 Git 历史。
- 同 Case 字段冲突：保留双方版本（`git show :2:`/`:3:`），按字段 diff 决定；不能整份取一边。
- 生成物冲突：还原到 base，源文件重提；由 main job 重建。
- 检查红但作者认为误报：不能绕过；修脚本/阈值走独立 PR；紧急情况用管理员 bypass，事后记录。
- 更新分支/检查失败：修分支后重新更新；不要在旧 base 上 rebase 生成物。

### 7.8 验收

- 构造 A 先合入、B 后合入：B 的旧 decision 必须失败（退出 1），刷新后通过；
- 两分支改同一 Case 不同字段：字段 diff 报告；改同一字段：退出 3；
- 同路径 add/add：退出 3 并列出双方；
- 删除/重命名 + 对侧引用：报告 dangling；引用仍存在 → 失败；
- PR 改 `knowledge/_index.yaml`：生成物守卫红；
- 分支落后：平台禁止合入（测试仓库验证）；
- 缺检查/检查红：平台禁止合入；
- `changes` 失败：`kb-required` 红，不能放行；
- bot 能推生成物；人类不能绕过。

---

## 8. Provenance：可追溯、完整性、可恢复、证据独立

### 8.1 四个概念分开

| 概念 | 问题 | 能进 Git 的保证 |
|---|---|---|
| 可追溯 Traceability | 这条知识从哪来、经过谁 | 记录来源（draft UUID、session、deployment、upstream）；可查 |
| 完整性 Integrity | 这份材料字节是否被改 | 只有材料可被验证者访问时，哈希才有意义 |
| 可恢复 Recoverability | 被舍弃/原始信息还能不能找到 | 只有目标在 Git/耐久存储且可访问时，才能承诺 |
| 证据独立 Independence | 两条验证是否同一次事件 | 需要稳定 event_id；否则只能写“未知/声明” |

**不做**：CI 检查一个 `deployment_id + draft_id + hash` 却访问不到本地草稿——这是假验证。

### 8.2 持久化策略（选择混合，最小保证）

| 材料 | 存哪 | 检查什么 | 承诺级别 |
|---|---|---|---|
| Case 草稿的结构化内容（已脱敏） | 可选提交到 `postmortems/materials/<case_id>/<draft_uuid>/case.yaml` | 存在、sha256 匹配 | `verified` |
| 复盘摘要（已脱敏） | 可选提交同一目录 `postmortem.md` | 存在、hash | `verified` |
| 原始日志/trace/客户材料 | 留在本地或私有耐久存储 | CI 不检查 | `local-only`/`archive-declared` |
| 被舍弃内容的摘要 | provenance 的 `dropped[]`，目标若是 Git 文件则校验 | 目标存在/hash | `verified` 或 `declared` |
| 外部证据 | URL/issue/PR | 只校验格式与可达性（可选） | `declared` |

#### 8.2.1 备选与取舍

| 方案 | 做法 | 优点 | 缺点/结论 |
|---|---|---|---|
| 1. 把脱敏源记录随 PR 提交 | 每份材料都进 `postmortems/materials/` | CI 可校验、可恢复 | 仓库膨胀；原始日志有隐私风险；不是所有材料都适合公开 |
| 2. 只存最小 manifest | 只存 hash/指针，不存材料 | 轻、无隐私 | hash 无法验证不可访问文件；可恢复性只是声明 |
| 3. 外部耐久归档 | 私有对象存储/工单系统 | 原始材料可留 | CI 无法访问；跨团队权限；生命周期与仓库不同 |
| 4. 明确限制保证 | 只做清单与档位 | 诚实、成本最低 | reviewer 只能看到“声明”，不能复核字节 |

**选择：2 + 1 + 4 的组合**——manifest 必交；结构化、已脱敏的 Case/复盘**可选**提交，标 `verified`；
原始材料留在本地/私有归档，标 `local-only/declared`。方案 3 作为部署选项（`archive_ref`），不假装 CI
能验证。这样“可追溯”总是成立，“完整性/可恢复”只在材料可访问时承诺。

规则：

1. 每个**新增/合并/改名**的 Case 必须有 `postmortems/provenance/<case_id>.yaml`；旧 Case 的普通字段
   修改不强制补 provenance（除非本次发生合并/改名）；
2. 材料默认**不强制**提交；提交的材料必须是脱敏后的结构化内容，禁止原始客户日志；
3. `recoverability` 三档：`verified`（目标在 Git、hash 匹配）、`declared`（声明在私有存储，CI 不验）、
   `local-only`（只在本地，CI 不验）；reviewer 在 PR 上能看到档位；
4. 不把 `local-only` 写成 `verified`；groom 摘要统计各档位数量，作为“证据债”观测；
5. **消费后不要立即删除 complete draft**：至少保留到 PR 合入、provenance 已记录/材料已提交之后；
   清理前确认 `recoverability` 档位；这是流程约束，CI 无法验证。

### 8.3 Manifest 结构

```yaml
case_id: VLLM-ASC-12345
decided_at: "<date>"
owner: <reviewer>
decision: merged            # new | merged | renamed | archived | superseded
lineage:
  supersedes: [VLLM-ASC-10111]   # 被合并的旧 ID
  merged_into: null
  renamed_from: null
materials:
  - draft_id: 6f1c...
    deployment_id: 6a2f...
    session: "<session-id>"
    files:
      - path: postmortems/materials/VLLM-ASC-12345/6f1c.../case.yaml
        sha256: ...
        committed: true
      - path: "traces/<session-id>.yaml"
        committed: false
        recoverability: local-only
    fields:
      symptoms: [6f1c...]
      fix: [6f1c...]
      compat: [6f1c...]
      diagnosis: [6f1c...]
    dropped:
      - field: diagnosis
        reason: 与已有步骤重复
        destination: null
        recoverability: declared
evidence:
  - event_id: "feedback:<session-id>:1"
    kind: feedback
    independent: false
    note: 与 material 2 同一次现场回报
  - event_id: upstream:vllm-project/vllm-ascend#10188@merged
    kind: upstream-fix
    independent: true
counts:
  usage: historical        # 使用记录按 Case ID 保留，不迁移
  incident_key: upstream:vllm-project/vllm-ascend#10303
  merge_note: 两条 Case 同一事故，但计数不互相累加
```

字段约定：

- `fields` 是**顶层字段**级归属：每个字段给一个 draft UUID 列表；`fix/root_cause/severity` 这类标量
  字段若来自多份材料，写 `merged: true` 并在 `note` 说明拼接依据；`symptoms/diagnosis` 这类列表字段
  若来自多份材料，**必须**写 `merged: true`，可选 `items`（`{symptoms: {0: uuidA, 1: uuidB}}`）做逐项
  归属。`verify_provenance` 检查“每个字段至少一个来源、来源都在 materials、multi-source 有 merged 标记”；
  它不证明字节级归属，reader 不能把 `fields` 当成“这段文字一定来自该 draft”的证明。
- `dropped[].destination` 若填 Git 路径，`recoverability: verified` 且检查存在/hash；否则只写
  `declared`/`local-only`。
- `event_id` 格式：`feedback:<session>:<n>`（n = 该 session 的 feedback 事件在 trace 中从 1 开始的序号）、
  `upstream:<repo>#<issue/pr>@<state>`、`fixture:<case_id>`、`report:<path>#<sha>`。没有 event id 写
  `none`，不编造。旧平铺 draft 或没有 UUID 的材料用 `legacy:<case-id>:<filename>` 作为 `draft_id`。
- `incident_key` 用于事故级去重（upstream 或脱敏事故号）；它不是 Case ID，不替代 Case ID。
- `counts.usage: historical`：**不重写历史使用记录**；`verify_entry_activity` 通过 `redirects.yaml`
  接受已改名/合并的旧 ID；事故级指标由 manifest 的 `incident_key` 聚合，不把两个 ID 的计数相加。

### 8.4 检查 `verify_provenance.py`

能机械检查：

1. `<case_id>.provenance.yaml` 存在，`case_id` 与文件名/Case 一致；
2. `lineage.merged_into/supersedes` 指向的 Case 存在或已归档；`renamed_from` 在 `redirects.yaml`
   有映射；反向链接存在；
3. `materials[].files` 中 `committed: true` 的文件存在、sha256 匹配、大小合理；
4. `dropped[].destination` 若 `recoverability: verified`，存在且 hash 匹配；
5. `evidence[].event_id` 格式合法；同一 event_id 不被两个 active Case 标为 `independent: true`
   （共享证据必须 `independent: false` 并有 note）；
6. `fields` 的每个 key 是 Case 的已知字段；每个 source draft_id 出现在 `materials` 中；多来源字段
   必须有 `merged: true`，否则失败；`items` 若存在，索引必须落在字段长度内；
7. `incident_key` 若存在，同一 incident 下的 Case 不重复计入（供观测脚本，不在本检查阻断）。

**不检查**：`committed: false` 的本地文件字节；`recoverability: declared/local-only` 的真实性；
`independent` 的语义正确性（人可撒谎）；字段内容是否真的来自该 draft（只有人/复核能判断）。

### 8.5 改 ID / 合并 / 归档

- `rename_case.py <old> <new>`：
  1. `git mv` 文件；改 `id`；更新 `ref_knowledge`/reference `sources[].cases`/fixture `case_id`；
  2. 更新/移动 provenance 文件名与 `case_id`，写 `lineage.renamed_from`；
  3. 追加 `postmortems/redirects.yaml`：`{old_id, new_id, at, reason}`；
  4. 不重写 `metrics/entry-activity.d/*` 历史行；`verify_entry_activity` 认 redirects；
  5. 更新 `traces/*.yaml`（本地，best-effort；CI 不验），打印未处理的本地文件；
  6. 若改到 `eval/golden/*.fixture.yaml` 的 `case_id`：夹具字节变化会让 `eval-scorecard`/`holdout`
     红。工具只改字节并在输出里提示；封存夹具需要维护者 `holdout.py --reseal` 且 PR 带
     `holdout-change` 标签。**rename 工具不能自动 reseal**。
- 合并两条 Case：`provenance` 的 `lineage.supersedes` 写旧 ID；旧 Case 移到 `_archive/` 或删除；
  `verify_references`/`verify_entry_activity` 通过 redirects 解析历史。
- 归档：`_archive/` 保留 ID；`verify_entry_activity` 已允许 `_archive/`；provenance 写
  `decision: archived`；不把归档当成“计数迁移”。
- 计数：历史使用记录保留在旧 ID；事故级指标按 `incident_key` 聚合；**禁止把两个 ID 的 resolved 相加**。
  如果需要在 Case 分数上体现合并，用 `incident_key` 派生一个只读视图，不改原计数。

### 8.6 Trace 限制

- `traces/` 本地、gitignored、无 CI；provenance 引用的 trace 只能 `local-only`；
- 交接包（`check_handoff.py`）可携带 trace，但仍是本地材料；
- 不把 trace 当“可验证证据”；reviewer 看到的是 manifest 的档位，不是原始 trace；
- 需要可验证证据时，提交**脱敏的结构化摘要**到 materials，而不是原始 trace。

### 8.7 隐私

- materials 只允许脱敏后的 Case/摘要；禁止原始日志、IP、账号、客户名；
- 提交前走 `to-postmortem` 的 redact 步骤；provenance 的 `redaction: {by, at, note}` 可选但推荐；
- 私有部署可把 materials 排除在公开仓之外（`scope: internal_only`）；此时 `recoverability: declared`，
  不假装 `verified`。

### 8.8 验收

- 新增 Case 无 provenance → 失败；
- `committed: true` 的文件被改一字节 → 失败；
- `dropped.destination` 指向不存在的 Git 文件却标 `verified` → 失败；标 `declared` → 通过；
- 两个 Case 用同一 event_id 且都 `independent: true` → 失败；
- 改名后引用/夹具/使用记录/redirects/provenance 全部一致；旧 ID 不再悬挂；
- 归档重复 Case：`verify_entry_activity` 通过、不报错，但观测报表把两个 ID 归到同一 `incident_key`；
- 不提交 materials 的 Case：通过，但 `recoverability: local-only` 被统计。

---

## 9. 指标、身份与缺陷修复

### 9.1 E10 同期号快照

- 期号加入部署短 ID：`<week>-live-<MMDD>-<deployment8>`；`verify_metrics.LIVE_PERIOD_RE` 扩展为
  可选后缀；旧文件保持合法（正则兼容）。
- `deployment.id` 在 `deployment.yaml` 首次生成；同一部署的多个 clone 若复制了 `deployment.yaml`，
  应各自重新生成（文档写明）；`doctor.py` 提示重复 id 的风险（无法全局检测，只提示）。
- `build_timeline` 继续拒绝重复 `period`；两个部署的同周读数成为两个 period，不再互相覆盖。
- 加 `metrics/timeline.d` 的 period 唯一性检查已有；不新增“缺期”硬门（无诊断的周本来可以没有读数）。

### 9.2 E11 数字 SHA

- `settle_trace_feedback.py` 写 `checkout/kb_rev` 时强制字符串（或 `yaml.safe_dump` 时加引号）；
- `entry_activity.aggregate` 在 `sorted()` 前 `str()` 归一；
- 回归测试：一行 `checkout: 8577483`、一行 `checkout: 55c20dc`，生成器必须成功；
- 同类问题：所有“短 SHA/数字型 ID”写入 YAML 的地方都加引号（用 `safe_dump` 的引号策略或显式 `str`）。

### 9.3 E12 快照与校验器

- 二选一（推荐前者）：
  1. 把 `external_record_violations_total` 加入 `verify_metrics` 白名单，并在 `metrics/gates.yaml`
     的 `metric_strength` 声明 6 个指标的强度档；
  2. 从 `metrics_snapshot.py` 输出中移除这些指标（会丢可观测性）。
- 加一条测试：`metrics_snapshot.py --emit-yaml` 的输出写入临时 `timeline.d` 后，
  `verify_metrics.py --check` 必须通过。这样生成器与校验器不再漂移。

### 9.4 E13 平台强制

见 §7.3；这是 P0，且需要管理员权限。

### 9.5 E14 reader contract

见 §5.4；B 必须复用同一 reader（验证报告已抓到 B 消费未完成草稿）。

### 9.6 生成物重建心跳

- 新增 `scripts/check_main_freshness.py`：在 main 上跑 `rebuild_generated.py --check`，若 dirty/失败，
  开 issue（或写 `metrics/generated-freshness.yaml` 并由周报读取）；`workflow_dispatch` + 每日 schedule。
- 它不替代 post-merge job；它是 job 失败/未配置时的告警。
- 失败形态：main 的索引缺新 Case，诊断看不到；心跳使“静默”变成“可见”。

### 9.7 观测（P2）

- 先有 decision 文件与 event_id，再谈指标；
- 候选准确率 = 有 decision 的重复对数 / 提名的 mandatory+high 对数；
- 候选漏报 = 标注集里未被提名的重复对；需要真实标注集（≥30 对），不能用合成数据报生产数字；
- 合并返工率 = 合并后又被拆开/改写的 Case 数 / 合并数（从 provenance lineage 与 Git 历史算）；
- 合并后误诊率 = 合并 Case 的 misdiagnosed / 使用次数（按 incident_key 聚合，不按 ID 相加）；
- 证据重复率 = 同 event_id 被多个 Case 引用的比例；
- 所有数字标注样本来源与时间；没有数据就写“无数据”。

---

## 10. 端到端工作流（A/B 故事）

1. **诊断**：A、B 各自在独立 clone；会话开始 `kb_sync.py --check`，trace 记录 `kb_rev`；若落后，
   提示但不中途改库。各自产出 trace。
2. **沉淀**：A/B 各自 `inbox_put.py new`（UUID 目录）→ 写三文件 → `finish`（DONE+hash）。
   两个同名 Case 不再互相覆盖；未完成/损坏目录不会被消费。
3. **groom 前同步**：`kb_sync.py --require-fresh`；`pr_radar.py` 拉开放 PR（可选）；groom 只消费
   `complete`/`legacy_flat`。
4. **B 生成候选**：`find_duplicates.py --include-open-prs`（如有）→ mandatory/high/low；展示预算与
   overflow ack；reviewer 逐对写 decision（new/variant/covered/deferred/separate）。
5. **PR**：`verify_decisions.py` 检查覆盖；`merge_recheck.py` 生成/刷新 decision 的 `main_sha`；
   源文件 only；`kb_sync --require-fresh`；提 PR。
6. **main 前进**：另一个 PR 合入；B 的分支落后。
7. **合入检查**：B 更新到最新 base（up-to-date）；`kb-required` 重跑：
   `merge_recheck` 对最新 base 重跑；decision 过期 → 红；B 刷新后重跑。
8. **平台强制**：required `kb-required`、1 非作者批准、dismiss stale/last-push approval、分支最新
   （P0）；缺一不能合。merge queue 是 P1 可选，不替代 P0。
9. **合入后**：`rebuild-generated` 重建索引/路由/timeline/entry-activity 并提交；`check_main_freshness`
   每日心跳；失败开 issue。
10. **收尾**：`rename_case.py`（如有改 ID）更新 refs/fixtures/usage/provenance/redirects；
    provenance manifest 进 Git；指标按 incident_key 聚合；`verify_provenance`/`verify_references`/
    `verify_entry_activity` 通过。

---

## 11. 实施优先级与工作量

> 估算假设：现有团队 1–2 人熟悉仓库；不含评审等待；不确定性 ±30%。开发人天不含平台管理员操作。

### P0 — 阻止已确认的静默丢数据 + 让检查可强制（2–3 周）

| # | 工作 | 文件/模块 | 依赖 | 难度 | 人天 | 测试 | 验收 | 需管理员 | 迁移/兼容 |
|---|---|---|---|---|---|---|---|---|---|
| P0-1 | 规则集：`kb-required` 聚合、批准、up-to-date、bot bypass；去掉 workflow 级 `paths`；`pr-template` 并入 | `kb-checks.yml`、`pr-template.yml`、ruleset | 管理员 | 中 | 2–3 | 测试 PR：缺检查/红/落后/批准失效/bot 推送 | 平台测试全部通过 | 是 | 无代码迁移 |
| P0-2 | E11/E12 + main 心跳 | `settle_trace_feedback.py`、`entry_activity.py`、`metrics_snapshot.py`、`verify_metrics.py`、`metrics/gates.yaml`、新 `check_main_freshness.py`、workflow | 无 | 低 | 2–3 | 单测：数字 SHA；快照输出过校验；心跳失败开 issue | 生成器不崩；周快照能过 CI | 否 | 旧 timeline 文件兼容 |
| P0-3 | 草稿协议 + reader | 新 `draft_queue.py`、`inbox_put.py`、`deployment_id.py`；`to-postmortem`、`issue-ingest`、`groom`、`sediment_batch`、两个面板 | P0-1 不必须 | 中 | 5–7 | 8 并发、3 崩溃、hash、reopen、legacy、面板契约 | §5.9 全过 | 否 | 旧平铺永久兼容 |
| P0-4 | 最小 C：merge_recheck + decision + verify_decisions；同路径/同 ID/字段 diff/过期 | 新 `case_match.py`（最小）、`case_diff.py`、`merge_recheck.py`、`verify_decisions.py`；PR 模板加 decision 区块；`kb-required` 接入 | P0-2（必需）；P0-1（仅“required”需要） | 中高 | 4–6 | 六场景、过期、同字段、删除/重命名、生成物 | §7.8 全过 | 是（required check） | decision 从新 PR 开始 |

P0 开发合计：**13–19 人天**；管理员 1–2 天；测试/评审 3–5 天。

### P1 — 多贡献者安全整合（2–3 周）

| # | 工作 | 文件/模块 | 依赖 | 难度 | 人天 | 测试 | 验收 | 需管理员 | 迁移 |
|---|---|---|---|---|---|---|---|---|---|
| P1-1 | B 完整：tiers、展示预算、overflow ack、跨类/跨 ns 理由、root/fix 信号、PR radar | `find_duplicates.py`、`case_match.py`、`pr_radar.py`、groom/模板 | P0-3、P0-4 | 高 | 6–9 | D1–D11 + 真实标注集；溢出 ack；radar 降级 | 9/9 必审展示；hidden high 有 ack；D11 不展示 | 否 | 旧草稿只读 |
| P1-2 | Provenance + rename + redirects | `verify_provenance.py`、`rename_case.py`、`postmortems/README`、模板 | P0-4 | 中高 | 4–6 | manifest 检查、事件重复、改名/归档、local-only | §8.8 全过 | 否 | 旧 Case 不追溯，新/合并强制 |
| P1-3 | E10 期号 | `deployment.yaml`、`metrics_snapshot.py`、`verify_metrics.py`、`build_timeline` | P0-2 | 低 | 1–2 | 两部署同周、旧期兼容 | 不覆盖、不假绿 | 否 | 旧期文件兼容 |
| P1-4 | 面板契约测试/收敛 | 两个 panel、fixtures | P0-3 | 中 | 2–3 | 同一 fixture 双实现 | 显示一致 | 否 | 无 |

P1 开发合计：**13–20 人天**。

### P2 — 观测与维护（1–2 周）

| # | 工作 | 文件/模块 | 依赖 | 难度 | 人天 | 验收 |
|---|---|---|---|---|---|---|
| P2-1 | 决策指标 + 标注集 + 月度报告 | `metrics`、decision、eval 标注集 | P1-1/2 | 中 | 4–6 | 5 个指标可算，样本来源标注 |
| P2-2 | 合并/事故级计数视图 | `incident_key`、`entry_activity` 只读视图 | P1-2 | 中 | 2–3 | 不重写历史，不重复计数 |
| P2-3 | 文档/技能/模板收尾 | docs、skills、templates | 全部 | 低 | 2–3 | 新成员按文档可跑 |

P2 开发合计：**8–12 人天**。

### 可独立实施与依赖

- **可独立实施（不依赖平台）**：P0-2（E11/E12/心跳）、P0-3（草稿协议 + reader + 面板）、P1-3（E10）、
  P1-4（面板契约）、P1-2 的 manifest/rename（在 P0-4 之后）。
- **可在 report-only 下先做**：P0-4 的 `merge_recheck`/`verify_decisions`（不设 required，只收集误报）；
  P1-1 的 B 完整版（依赖 P0-3）。
- **必须等平台**：P0-1 的 required check/批准/up-to-date；P0-4 的“阻止合入”依赖 P0-1。
- **依赖链**：P0-3 → P1-1；P0-4 → P1-2；P0-2 → P1-3；P0-1 → 所有“强制”声明。
- **可并行**：P0-1（管理员）+ P0-2/P0-3（开发）可并行；P1-1 与 P1-2 可在 P0-4 后并行。

### 总估算

- 开发：**34–51 人天**（P0 13–19 + P1 13–20 + P2 8–12）；中间值约 42。
- 平台/管理员：2–4 人天（ruleset、up-to-date、bypass、测试仓库；queue 可选）。
- 评审/发布/培训：5–8 人天；迁移与兼容：2–3 人天。
- 运行成本：每次沉淀 +2 条命令；每次 groom 多 20–40 分钟候选复核；每个 PR 多 5–15 分钟决定/刷新；
  每周一次心跳与例外处理。
- 与 V1 的 20–30 人天相比，V2 增加了 decision 检查、radar、provenance 检查与契约测试；减少了
  独立六轴比较器与全库关键词扫描。**估算是工程判断，不是承诺**；P0 先做可独立验证。
- 不确定性主要来自：两套 panel 实现的实际改动量、真实标注集与阈值调优、平台 ruleset/up-to-date 的测试
  返工。若平台批准推迟，P0 的代码部分（P0-2/P0-3/P0-4 report-only）约 **11–16 人天**可先落地，
  但不能宣称“阻止合入”。

---

## 12. 集成点清单

| 区域 | 文件 | 改动 |
|---|---|---|
| 诊断 | `skills/diagnose/SKILL.md`、`references/diagnosis-trace.md` | `kb_sync --check`、`kb_rev/kb_stale` 记录 |
| 沉淀 | `skills/to-postmortem/SKILL.md`、`skills/issue-ingest/SKILL.md` | `inbox_put new/finish`；报告 UUID 路径；不再直接写平铺 |
| Groom | `skills/knowledge-groom/SKILL.md` | reader、B、decision、overflow ack、`kb_sync --require-fresh`、radar |
| 草稿 | `postmortems/inbox/README.md`、`.gitignore`（无需改） | 目录/DONE/reader；legacy 说明 |
| 比较器 | 新 `scripts/case_match.py`、`scripts/_lexical.py`、`scripts/build_index.py` | 复用 token/sig；build_index 改为引用 |
| B/C | 新 `find_duplicates.py`、`merge_recheck.py`、`verify_decisions.py` | 生成/展示/决定/退出码 |
| Provenance | 新 `verify_provenance.py`、`rename_case.py`、`postmortems/README.md`、`postmortems/redirects.yaml` | manifest/lineage/redirects |
| CI | `.github/workflows/kb-checks.yml`、新 `merge-recheck` job、`kb-required`；`pr-template.yml` 并入 | 去 workflow `paths`；新增 required；`case-structure` 加 `verify_decisions`/`verify_provenance`（P1）；把模板检查搬进同一 workflow |
| 模板 | `.github/PULL_REQUEST_TEMPLATE/knowledge_intake.md`、`knowledge_modification.md` | 查重/决定/复核/来源去向区块（machine block 可选） |
| 平台 | ruleset、CODEOWNERS、DEPLOY_KEY | 批准/必需检查/up-to-date/bypass（queue 可选） |
| 面板 | `dsh-plugins/ascend-panel/panel-host.js`、`dsh-plugins/dsh-sleuth-panels/lib/index.js` | reader 契约 + 契约测试 |
| 指标 | `deployment.yaml`、`metrics_snapshot.py`、`verify_metrics.py`、`metrics/gates.yaml`、`build_timeline.py` | id/期号/强度/兼容 |
| 文档 | `docs/guide/git-workflow.md`、`docs/guide/metrics.md`、`docs/spec/writing-norms.md`（如需） | 新流程、命令、限制 |

---

## 13. 验收测试（统一入口）

1. **A**：`tests/test_inbox_protocol.py`——8 并发、3 崩溃、hash、reopen、legacy、两 panel fixture。
2. **B**：`tests/test_find_duplicates.py`——D1–D11：
   - 9 个必须展示（mandatory+high，含 D2）；
   - D11 不展示；
   - hidden high = 0 或 ack；hidden low 有计数；
   - 跨类/跨 ns 理由成立；同 ID/同路径/同 upstream 永远 mandatory。
   另加 ≥30 对真实标注样本（P1 才要求，合成数字不作生产结论）。
3. **C**：`tests/test_merge_recheck.py`——六场景 + 过期 + 同字段/不同字段 + 删除/重命名 + 生成物；
   `verify_decisions` 覆盖/ack/freshness；平台测试 PR（非本地脚本）验证缺检查/红/落后/批准失效。
4. **Provenance**：`tests/test_provenance.py`——manifest、hash、dropped、event 重复、改名/归档、
   local-only；`rename_case` 后 refs/fixtures/usage/redirects 全绿。
5. **E10–E14**：两部署同期、数字 SHA、快照过校验、ruleset 测试、reader 契约。
6. **回归**：`python3 scripts/rehearse_evolve_loop.py`（现有端到端演练）与 CI 全量。

---

## 14. 运行成本、风险与回滚

### 14.1 成本

- 每次沉淀：`new` + `finish` 两条命令；UUID 路径比 Case ID 难读，但报告显示 title/session。
- 每次 groom：B 生成 2–3 秒；复核 20–40 分钟（21 核心 + 10 低优先，合成样本）；overflow ack。
- 每个 PR：decision 文件编写/刷新 5–15 分钟；C 运行秒级；up-to-date 重跑。
- 平台：ruleset/up-to-date 配置 1–2 天（queue 可选）；CODEOWNERS owner 时间。
- 维护：决策模板、阈值、标注集、两个面板契约测试；每季度校准一次。

### 14.2 主要风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 平台不批 required checks/up-to-date | C 无强制，回到“报告” | 评审时明确决策；没有平台改动就只承诺“检测”，不承诺“阻止” |
| 审核疲劳 | 走过场 | mandatory 优先；high 预算 30；low 只报数；每季度抽样 |
| 候选漏报 | 重复仍入库 | 明确不保证；共享来源/ID/路径 mandatory；真实标注集评估；合并后审计 |
| decision 造假 | 机器门失效 | 不校验语义；reviewer 非作者；抽审；PR 模板要求证据 |
| 面板漂移 | 新草稿不可见 | 同一契约 + 契约测试；长期合并实现 |
| 本地-only 证据 | 无法复核 | 档位如实标注；可选提交脱敏材料；不假装 verified |
| 规则集 bot 被挡 | 生成物停更 | bypass 仅 deploy key；心跳告警；job 失败红 |
| Windows/NFS 语义 | mkdir/replace 不原子 | 只用本地 NTFS/常见 FS；NFS 明确不支持；文档写 |
| 迁移成本 | 旧草稿/旧 Case | 永久兼容；旧 Case 不追溯 provenance；redirects |

### 14.3 回滚

- 平台：把 `kb-required` 从 required 移除、恢复原 ruleset；代码与数据不受影响。
- 草稿：保留旧平铺 reader；停用 `inbox_put` 后仍可手工写平铺（回退到旧行为，不丢已有目录）。
- B/C：脚本非必需；关闭 CI job 即回退到旧检查；decision 文件保留为历史。
- Provenance：检查可降级为 report-only（不阻断）；manifest 保留。
- 生成物：`rebuild_generated.py --sync` 或主干 job 重建；生成物不进 PR 的纪律不变。
- 每一步都先做“report-only”观察一轮，再改为 required；回滚不需要重写历史。

---

## 15. 需要拍板的事项与未验证假设

### 15.1 拍板

1. 是否批准平台强制（required `kb-required`、1 非作者批准、up-to-date（merge queue 可选）、DEPLOY_KEY bypass）。
2. 是否接受“P0 先做 A + 最小 C + E11/E12/心跳”，B 完整版放 P1。
3. 是否接受 provenance 的“committed manifest + 可选脱敏 materials + local-only 如实标注”政策。
4. 谁承担 reviewer/owner（CODEOWNERS）与每周 groom 的 20–40 分钟。
5. 是否接受“候选不能保证召回、CI 不能判断语义”的公开声明。

### 15.2 未验证（必须在生产前验证）

- GitHub ruleset/up-to-date/approval/bypass 的真实行为（需测试仓库与管理员；queue 若启用另验）。
- PR radar 在真实 open PR 上的覆盖率、限流、378+ ref 的增量成本（只验证了 1 个 PR head）。
- 两个面板对新 reader 的显示一致性（需 DSH host）。
- 真实库上的 B 阈值/工作量（合成夹具的 root/fix 重合偏高，数字偏乐观）。
- Windows/NFS 的 `mkdir`/`os.replace` 语义；只测了 NTFS。
- 规模：>500 Case、>50 并发 draft、>100 open PR 时的运行时间与内存。
- 迁移旧 Case 的 provenance 追溯成本（本文只强制新/合并 Case）。

### 15.3 结论

V2 的核心不是“更多脚本”，而是三条可执行保证：**草稿有身份且读者严格**、**候选有优先级且人写决定**、
**合入有平台强制且对最新状态复核**。Provenance 只承诺能验证的部分；指标在数据存在后再报。
如果平台强制不能落地，V2 只能提供“检测与记录”，不能提供“阻止”；评审时必须这样表述，不能用脚本
的存在替代平台的门。


