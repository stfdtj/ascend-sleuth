# 09 — 实现设计与迁移方案

这份文档只回答三件事：V2 落地后系统长什么样、要改哪些结构、现有草稿和历史数据怎么办。
不写工期，不写人员分工。

---

## 1. 目标结构

### 1.1 草稿

```text
postmortems/inbox/<uuid>/
  case.yaml          # 与正式 case 同形，顶层是 cases:
  postmortem.md      # 人读复盘
  sources.yaml       # 来源、条件、验证、字段摘要
  DONE               # 最后写；含 completed_at 和三文件 sha256
```

- `<uuid>` 就是 Draft ID，永不复用。
- `sources.yaml.draft_id` 必须等于目录名。
- `DONE` 是完成标记；`DONE` 存在后三个文件不可改，修改走 `reopen`。
- 旧平铺草稿仍是：

```text
postmortems/inbox/<case-id>.case.yaml
postmortems/inbox/<case-id>.md
```

### 1.2 决策与 provenance

```text
postmortems/decisions/<case-id>.yaml
postmortems/provenance/<case-id>.yaml
postmortems/materials/<case-id>/<draft-uuid>/...
```

- `decisions/` 和 `provenance/` 进 Git；`materials/` 只有在脱敏后才进 Git。
- 草稿目录、`DONE`、本地材料仍不进 Git；`.gitignore` 已覆盖 inbox。
- `knowledge/`、`references/`、生成物的格式不变；检索路径不变。

### 1.3 读写边界

| 对象 | 写入口 | 读入口 | 进 Git |
|---|---|---|---|
| 草稿 | `inbox_put.py new/finish/reopen` | `draft_queue.py` | 否 |
| 决策 | `verify_decisions --init` 或人手写 | `verify_decisions` / `merge_recheck` | 是 |
| provenance | `to-postmortem`/groom/人手写 | `verify_provenance` | 是 |
| 正式 case | groom 升格 | 现有检索 | 是 |
| 生成物 | 主干 rebuild job | 现有检索 | 是 |

---

## 2. 运行面改动

### 2.1 新增脚本

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `scripts/draft_queue.py` | 唯一 reader；返回 `complete/incomplete/corrupt/superseded/legacy_flat` | 消费方不得直接读 inbox 文件 |
| `scripts/inbox_put.py` | writer：`new/finish/list/reopen/abort/migrate` | `mkdir` 独占；`DONE` 原子替换；完成后不可改 |
| `scripts/case_match.py` | B/C 共用比较器 | 复用 `_lexical.tokens_of`、`build_index.sig_literals` |
| `scripts/find_duplicates.py` | B 生成、分层、展示、溢出计数 | mandatory 不受展示上限影响 |
| `scripts/merge_recheck.py` | C：base/head、字段 diff、decision 检查 | 退出码区分冲突/缺决策/过期/生成物 |
| `scripts/case_diff.py` | 同 case 字段 diff | 只给字段，不给“谁对” |
| `scripts/verify_decisions.py` | decision 覆盖、值、SHA/内容绑定、ack | 拒绝 `TODO`/空值/未知值 |
| `scripts/verify_provenance.py` | committed 哈希、local-only 标注、lineage、redirect | 不把 local-only 当可恢复 |
| `scripts/deployment_id.py` | 生成/校验 `deployment.id` | 不参与 Draft 唯一性 |

### 2.2 修改现有脚本

| 文件 | 改动 | 影响 |
|---|---|---|
| `scripts/sediment_batch.py` | `--inbox-path` 接受目录；回写 `submitted` 记录草稿目录 | 批处理不再假设平铺文件 |
| `scripts/settle_trace_feedback.py` | checkout/kb_rev 写成字符串；登记 event_id | 避免 E11；provenance 有事件锚点 |
| `scripts/entry_activity.py` | checkout 排序前统一转 str；redirects 读取 | 避免 E11；改 ID 后使用记录可解析 |
| `scripts/metrics_snapshot.py` | live 期号加 deployment 后缀 | 避免 E10；旧期号兼容读 |
| `scripts/verify_metrics.py` | 扩 live 白名单/强度检查 | E12 的生成物能过自己的校验 |
| `scripts/verify_entry_activity.py` | 无效 ID 先查 redirects | 改 ID/归档不再硬红 |
| `skills/to-postmortem/SKILL.md` | 产出改为 `inbox_put.py new/finish` | 新草稿不再写平铺文件 |
| `skills/issue-ingest/SKILL.md` | 同上 | 批量导入走同一 writer |
| `skills/knowledge-groom/SKILL.md` | 只消费 reader 的 `complete`/`legacy_flat`；报告 incomplete/corrupt | 不再半套草稿升格 |
| `dsh-plugins/ascend-panel/panel-host.js` | 读 reader JSON | 面板不再自己扫文件 |
| `dsh-plugins/dsh-sleuth-panels/lib/index.js` | 同上 | 两个面板共用契约 |
| `.github/workflows/kb-checks.yml` | 增加 `kb-required` 聚合 job；去掉 workflow 级 `paths`；把 `pr-template` 并入 | required check 覆盖所有 job |
| `.github/workflows/rebuild-generated.yml` | 生成物 bot 的 bypass 与 branch 规则 | 主干重建不被分支保护挡住 |

### 2.3 不改的东西

- `knowledge/` 的 case schema、`references/` 的类型与索引格式。
- 生成物 `_index.yaml`、读侧视图、triage tree、timeline、entry-activity 的格式。
- 检索算法与候选加载路径。
- 历史已合入的 case、reference、fixture、usage 记录不重写。

---

## 3. 现有 inbox 草稿怎么办

### 3.1 当前设计的选择

**不做强制批量迁移。** 旧平铺草稿继续以 `legacy_flat` 被读取：

- groom 可以消费，B 可以生成候选；
- 带 `legacy: true` 警告；
- 没有 UUID、没有 `DONE`、没有 sha256、没有 provenance；
- 不能证明“文件是完整的”，半套草稿仍可能被消费。

这是兼容成本最低的方案，但旧草稿不受 V2 的完成性保护。这个代价必须说清楚：**升级后新草稿受保护，旧草稿只是继续可用。**

### 3.2 哪些旧草稿建议迁移

按“是否会继续被修改/升格”分：

| 情况 | 处理 |
|---|---|
| 马上要 groom 升格 | 迁移到 UUID，再走新流程 |
| 还要补内容/改分类 | 迁移后 `reopen`，不要直接改旧文件 |
| 长期停着、内容完整 | 可以保持 `legacy_flat`，groom 时再决定 |
| 半套、YAML 损坏、缺 `.md` | 不迁移；reader 报 `incomplete/corrupt` 或 legacy 警告，人工清理 |
| 同一 case ID 有多份 | 不自动合并；逐份建 UUID，decision 里记录取舍 |

### 3.3 迁移工具的行为

`inbox_put.py migrate` 是**逐台 checkout** 的工具，不是 Git 操作：

```bash
python3 scripts/inbox_put.py migrate --dry-run   # 只读，输出计划
python3 scripts/inbox_put.py migrate --apply     # 逐份迁移
python3 scripts/inbox_put.py migrate --rollback  # 从 _legacy 放回
```

算法：

1. 扫描 `postmortems/inbox/*.case.yaml`；配对的 `.md` 必须存在。
2. 解析 case YAML；顶层 `cases` 非空；提取建议 case ID 和 `source_session`。
3. 对每份生成新 UUID；`sources.yaml` 写：
   - `draft_id`；
   - `source.kind: legacy-migration`；
   - `source.session`（有就写）；
   - `conditions`（能从 case 读多少写多少，读不到写 `unknown`）；
   - `verification: [{event_id: none, kind: legacy}]`；
   - `legacy_path` 和 `migrated_at`。
4. 复制 `case.yaml` 和 `postmortem.md` 到新目录；计算 sha256；写 `DONE`。
5. 把原平铺文件移到 `postmortems/inbox/_legacy/<case-id>/`；不删除。
6. 写迁移清单 `postmortems/inbox/_migration.json`（本机文件，不进 Git）。
7. `--dry-run` 不写任何文件；`--apply` 遇到已迁移的 case ID + 内容哈希相同则跳过，保证幂等。

迁移后的目录与新建草稿完全同形；groom/B 不需要知道它来自迁移。

### 3.4 写入切换

1. 先部署 reader（`draft_queue.py`）和兼容层；旧 writer 仍能写平铺。
2. 再更新 `to-postmortem`/`issue-ingest` 调 `inbox_put.py`；新产出只写 UUID。
3. 最后把 groom/面板切到 reader。
4. 旧 agent 仍可能写平铺；reader 继续支持 `legacy_flat`，`doctor`/groom 报告“新增平铺草稿”的数量，提示升级。
5. 不在 CI 里拦平铺草稿：inbox 是本地文件，CI 看不到；只能在本地入口和面板上提示。

### 3.5 手动更新一份旧草稿

不迁移也可以：

- 只是补内容：把旧文件内容复制到新 UUID 草稿，`finish` 后把旧文件移到 `_legacy`；
- 已经完成、要改：先迁移，再 `reopen`；
- 不要直接改一个已 `finish` 的 UUID 草稿；reader 会报 `corrupt`。

---

## 4. 现有 open PR 与已合入内容

### 4.1 open PR

- 已升格到 `knowledge/` 的 PR 不受 inbox 改动影响；受 C 影响。
- V2 上线后，C 要求 decision；旧 PR 没有 decision 时会返回 2。
- 处理方式：
  1. 对旧 PR 跑一次 `merge_recheck.py`；
  2. 有 mandatory/high pair 或 `both_modified` 的，跑 `verify_decisions --init` 生成骨架，作者补 decision；
  3. 没有 pair、没有同 case 修改的，不要求 decision 文件；
  4. 不自动给旧 PR 放行，也不自动写“已审”。
- 旧 PR 的草稿在作者本机，不在 Git；不需要迁移 PR 里的草稿。

### 4.2 已合入 case

- 不补 decision，不补 provenance，不改 case schema。
- 只有下一次修改该 case 时，才要求 decision；provenance 可在下一次沉淀时补。
- 历史 usage 记录不迁移；统计继续按原 case ID。
- rename/merge 的历史数据不回溯；新 rename 用 `rename_case.py` + redirects。

### 4.3 引用、fixture、usage

- 正常合入不改它们。
- rename 才触发迁移；当前设计里这是独立工具，不在 inbox 迁移范围。
- 不在迁移工具里改 holdout；封存夹具仍按原规则。

---

## 5. CI 与合并路径的结构改动

```text
PR
 ├─ changes（路径过滤）
 ├─ kb-checks（结构、引用、metrics、holdout）
 ├─ generated-guard（生成物守卫）
 ├─ merge-recheck（C，读 decision）
 └─ kb-required（needs: 全部；if: always()）
        └─ 分支保护只要求这一个 check
```

结构影响：

- workflow 级 `paths` 去掉，否则 docs-only PR 不触发 required check，永远等不到。
- `pr-template` 并入 `kb-checks`，否则模板检查可能被路径过滤跳过。
- `kb-required` 必须 `if: always()`，并显式把 skipped/failed 都判失败。
- 生成物重建 job 用 bot bypass；否则 bot 自己推 main 会被 required check 挡住。
- 1 名非作者 approval；dismiss stale review；up-to-date。
- `decision` 是 PR 里的一个 YAML 文件，不是 PR 描述；C 只读文件。

### 5.1 对现有 PR 的直接影响

- 旧 PR 第一次 rebase 后，C 会跑；缺 decision 就红。
- 生成物冲突不再由作者解决；主干 job 重建。
- PR 多一个 decision 文件，少一次“口头说查过了”。

---

## 6. 结构代价

### 6.1 代码面

- 新增约 10 个脚本/模块；修改约 6 个既有脚本、3 个 skill、2 个面板、2 个 workflow。
- 草稿路径从“一个文件”变成“一个目录 + 四个文件”；所有假设平铺路径的代码都要改。
- 两套读取路径（UUID / legacy）在兼容期同时存在；测试矩阵要覆盖两套。
- B/C 共用一个比较器，减少重复逻辑，但 C 的字段 diff 是新增代码。

### 6.2 数据面

- 不迁移任何已合入的 knowledge/reference/fixture/usage。
- 新增 `postmortems/decisions/`、`postmortems/provenance/` 两个进 Git 的目录；每个相关 PR 多 1–2 个小 YAML。
- `materials/` 可选；不提交时 case 只能是 `local-only`，不可恢复。
- 旧平铺草稿不强制迁移；长期保留兼容读取。

### 6.3 操作面

- 每台机器/每个 checkout 的 inbox 是本地件；迁移不能在一台机器上替所有人做。
- 迁移工具必须幂等；重复跑不能产生两份相同内容。
- 旧 agent 仍会写平铺；只能提示，不能靠 CI 拦。
- groom 多了一步：先看 reader 状态，再决定是否升格。
- 评审多了一步：读 decision 文件，确认不是 `TODO`。

### 6.4 失败与回滚

| 情况 | 回滚 |
|---|---|
| 新 reader 有 bug | 保留旧平铺读取路径；回退脚本 |
| 迁移写坏一份草稿 | `migrate --rollback` 从 `_legacy` 放回；不碰知识库 |
| 新 writer 有问题 | 临时恢复旧 writer；reader 仍能读平铺 |
| required check 误伤 | 暂时移除 required；不删 ruleset 其他规则 |
| decision 文件格式错 | 修文件重跑；不绕过 C |
| 生成物 bot 被挡 | 恢复 bot bypass 或手动跑 rebuild |

回滚不涉及知识库重写；最坏情况是回到 V1 的平铺草稿和“报告式”检查。

---

## 7. 验收清单

### 7.1 迁移

- 10 份平铺草稿：5 份完整、2 份缺 `.md`、1 份 YAML 损坏、2 份同 case ID。
- `--dry-run` 不写文件；计划列出可迁移/跳过/需人工。
- `--apply` 后：5 份变 `complete`；2 份仍 `legacy_flat` 或报缺文件；1 份报 `corrupt`；2 份各自独立 UUID。
- 再跑一次 `--apply`：不新增目录。
- `--rollback` 后：平铺文件恢复；UUID 目录可删；知识库不变。
- 两台 checkout 各跑一次：各自迁移，不共享 UUID，不产生跨机重复。

### 7.2 读写

- groom 只消费 `complete`/`legacy_flat`；`incomplete/corrupt` 只报告。
- B 不读未完成目录；legacy 带 `legacy: true`。
- 两个面板对同一 inbox 显示同一状态。
- `sediment_batch` 的 `submitted` 记录目录路径。

### 7.3 PR

- 旧 PR 无 decision：C 返回 2；补 decision 后返回 0。
- 旧 PR 无 pair：C 返回 0，不要求空文件。
- 同 case 两分支：C 返回 3（字段重叠）；disjoint 时要求 `same_case`。
- 生成物手改：C 返回 4。
- required check：缺 check/红 check/过期分支都挡住；bot 能推生成物。

### 7.4 回滚

- 移除 required 后，旧流程可合入。
- 新 writer 停用后，旧平铺仍能被 groom 读。
- `_legacy` 备份完整。

---

## 8. 不做的事

- 不批量重写所有 inbox 草稿；只对需要继续使用的逐份迁移。
- 不把草稿提交进 Git；inbox 仍是本地队列。
- 不迁移已合入的 case/reference/fixture/usage；不补历史 decision。
- 不给 legacy 草稿伪造 `DONE` 或哈希。
- 不自动写 decision 的结论；只生成骨架，内容由人填。
- 不改知识库索引格式，不引入第二套检索。
