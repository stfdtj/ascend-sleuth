# 13 — Real GitHub scenario plan and execution prompt

这个文件分两部分：

1. 给内部 AI 的 prompt（可直接复制）；
2. 真实 GitHub 测试计划（测试仓库、ruleset、workflow、场景、证据、判定）。

它对应的代码分支是 `kb/v2-core`（提交 `fdb4e45`），但测试仓库必须是**一次性私有仓库**，不能直接用生产仓库。

---

## 0. 给内部 AI 的 prompt

```text
你在一台有 GitHub 权限的工作机上执行一次“V2 真实 GitHub 场景测试”。

目标：
验证 GitHub 平台是否真的能按 V2 的假设阻止不合格合并，而不是只在本地 harness 里看起来能阻止。

硬约束：
1. 只在一个一次性私有测试仓库里操作。仓库名必须是 ascend-sleuth-v2-spike 或用户明确指定的测试仓库。
2. 不得修改生产仓库 pillumina/ascend-sleuth 的 ruleset、branch protection、workflow、main 分支或任何生产数据。
3. 不得把真实客户日志、trace、case、token、deploy key 私钥写进仓库或测试报告。
4. 每次执行会改变远程状态的操作前，先打印目标 repo 的 owner/name，确认它不是生产仓库。
5. 如果缺少测试仓库、第二个 GitHub 账号、管理员权限或 deploy key，不要假装通过；把对应场景标记 UNTESTED 并写明缺什么。
6. 不要为了“让测试通过”而关闭 required check、approval 或 up-to-date。失败也是结果。
7. 所有测试用合成 case，ID 用 VLLM-ASC-100xx，不要用真实 case。

输入：
- 代码来源：git@github.com:stfdtj/ascend-sleuth.git，分支 kb/v2-core，提交 fdb4e45。
- 测试仓库：由用户提供 owner/name；若没有，先停止并询问。
- 两个身份：作者 A、非作者评审人 B；若没有 B，approval 场景标记 UNTESTED。
- 可选：deploy key 或 GitHub App，用于 bot bypass 场景。

执行顺序：
1. 建测试仓库，复制 kb/v2-core 的 scripts/ 和最小 knowledge/ 样本。
2. 加测试用 .github/workflows/kb-checks.yml（按计划里的模板）。
3. 先记录“没有 required check”的基线：PR 可以不满足条件就合入。
4. 配置 ruleset：require PR、required check 只写 kb-required、1 名非作者 approval、dismiss stale review、require up-to-date、bot bypass。
5. 按计划跑 P1–P8；通过后再跑 P9–P11（V2 decision/C）；最后跑 P12（merge queue，若仓库计划支持）。
6. 每个场景记录：PR 编号、check run 名称与结论、review 状态、mergeStateStatus、ruleset JSON、失败 API 返回。
7. 结束前把证据写到 artifacts/github-spike/，输出一份 markdown 总结；测试仓库保留还是删除，先问用户。

判定：
- 只有“红灯时 merge 按钮/API 真的不可用”才算通过；
- 只有“缺 decision 时 C 真的失败”才算通过；
- 只有“skipped 没有被聚合 job 当通过”才算通过；
- 任何一项无法执行，写 UNTESTED，不写 PASS。

输出：
- 一段结论：哪些场景 PASS / FAIL / UNTESTED；
- 每个场景的证据文件路径；
- 生产启用前必须修的差异；
- 不要给时间估算，不要替团队做决定。
```

---

## 1. 测试仓库

### 1.1 创建

```bash
gh repo create <owner>/ascend-sleuth-v2-spike --private --clone
cd ascend-sleuth-v2-spike
```

不要 fork 生产仓库；fork 的 ruleset/权限行为可能和生产不同，且容易误操作。

### 1.2 目录

```text
.github/workflows/kb-checks.yml
scripts/
  case_match.py
  case_diff.py
  merge_recheck.py
  verify_decisions.py
  draft_queue.py
  inbox_put.py
knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-10001.yaml
postmortems/decisions/README.md
postmortems/inbox/README.md
.ci/fail          # 可选，测试红 job
.ci/skip          # 可选，测试 skipped job
```

从 `kb/v2-core` 复制脚本：

```bash
git clone --branch kb/v2-core git@github.com:stfdtj/ascend-sleuth.git /tmp/v2-src
cp /tmp/v2-src/scripts/case_match.py \
   /tmp/v2-src/scripts/case_diff.py \
   /tmp/v2-src/scripts/merge_recheck.py \
   /tmp/v2-src/scripts/verify_decisions.py \
   /tmp/v2-src/scripts/draft_queue.py \
   /tmp/v2-src/scripts/inbox_put.py \
   scripts/
```

### 1.3 基线 case

```yaml
cases:
  - id: VLLM-ASC-10001
    title: "310P bf16 startup failure"
    category: interrupt
    symptoms: ["bfloat16 is not supported", "npu-smi 310P"]
    quickly_check:
      primary:
        command_template: "grep -c 'bfloat16' {{log_path}}"
        expected: "regex:^[1-9]"
    root_cause: "310P does not support bfloat16"
    fix: "change dtype to float16"
    platforms: [A2-310P]
    compat:
      - framework: vllm-ascend
        ranges: ["==0.22.0"]
```

---

## 2. 测试 workflow

`.github/workflows/kb-checks.yml`：

```yaml
name: kb-checks

on:
  pull_request:
  merge_group:

jobs:
  changes:
    runs-on: ubuntu-latest
    outputs:
      docs: ${{ steps.diff.outputs.docs }}
      knowledge: ${{ steps.diff.outputs.knowledge }}
      fail: ${{ steps.diff.outputs.fail }}
      skip: ${{ steps.diff.outputs.skip }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - id: diff
        run: |
          set -eu
          base="${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}"
          git fetch --no-tags origin "$base" || true
          changed=$(git diff --name-only "$base"...HEAD)
          echo "docs=$(echo "$changed" | grep -qE '^docs/' && echo true || echo false)" >> "$GITHUB_OUTPUT"
          echo "knowledge=$(echo "$changed" | grep -qE '^knowledge/' && echo true || echo false)" >> "$GITHUB_OUTPUT"
          echo "fail=$([ -f .ci/fail ] && echo true || echo false)" >> "$GITHUB_OUTPUT"
          echo "skip=$([ -f .ci/skip ] && echo true || echo false)" >> "$GITHUB_OUTPUT"

  pass:
    needs: changes
    if: needs.changes.outputs.skip != 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          if [ -f .ci/fail ]; then echo "intentional failure"; exit 1; fi
          echo "pass"

  docs:
    needs: changes
    if: needs.changes.outputs.docs == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "docs check"

  merge-recheck:
    needs: changes
    if: needs.changes.outputs.knowledge == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install pyyaml
      - run: |
          base="${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}"
          git fetch --no-tags origin "$base" || true
          python scripts/merge_recheck.py --base "$base" --head HEAD --json

  kb-required:
    if: always()
    needs: [changes, pass, docs, merge-recheck]
    runs-on: ubuntu-latest
    steps:
      - name: check dependency results
        env:
          NEEDS: ${{ toJSON(needs) }}
        run: |
          python - <<'PY'
          import json, os, sys
          n = json.loads(os.environ["NEEDS"])
          bad = {k: v["result"] for k, v in n.items()
                 if v["result"] in ("failure", "cancelled")}
          if bad:
              print("failed/cancelled:", bad); sys.exit(1)
          if n["changes"]["result"] != "success":
              print("changes did not succeed"); sys.exit(1)
          if n["changes"]["outputs"].get("skip") == "true":
              print("skip marker set: pass job was skipped"); sys.exit(1)
          if n["pass"]["result"] == "skipped":
              print("pass job skipped"); sys.exit(1)
          if n["changes"]["outputs"].get("docs") == "true" and n["docs"]["result"] == "skipped":
              print("docs job skipped but docs changed"); sys.exit(1)
          if n["changes"]["outputs"].get("knowledge") == "true" and n["merge-recheck"]["result"] == "skipped":
              print("merge-recheck skipped but knowledge changed"); sys.exit(1)
          print("required ok")
          PY
```

注意：

- `kb-required` 是唯一 required check；不要单独要求 `pass` 或 `merge-recheck`。
- workflow 级没有 `paths`，docs-only PR 也会触发聚合 job。
- `pass` 的 skipped 要判失败；`docs`/`merge-recheck` 的合法 skipped 不能误判。
- 这个 workflow 只用于测试，不要直接当生产 workflow。

---

## 3. Ruleset

先用 UI 配，避免 API schema 猜错；配完导出：

```bash
gh api repos/<owner>/<repo>/rulesets > artifacts/github-spike/ruleset-before.json
```

目标：

- require pull request；
- required status checks: `kb-required` only；
- require branches to be up to date；
- 1 required approving review；dismiss stale reviews on push；require approval of most recent push；
- restrict direct pushes，bot/deploy key 在 bypass 列表。

导出后确认：

```bash
gh api repos/<owner>/<repo>/rulesets/<id> > artifacts/github-spike/ruleset.json
```

---

## 4. 场景

### P0 — 基线

不配 ruleset，开一个只改 README 的 PR，直接合并。记录“没有 required check 时能合”。这是对照，不是通过项。

### P1 — 缺 check

开 PR，关闭 Actions（或让 workflow 不触发），尝试合并。期望：`kb-required` 一直 pending，不能合。

### P2 — 红 check

在 PR 分支加 `.ci/fail`，推上去。`pass` 失败，`kb-required` 失败，不能合。

### P3 — skipped 应判失败

在 PR 分支加 `.ci/skip`，推上去。`pass` 被 `if` 跳过；`kb-required` 必须失败。若聚合 job 通过，说明它把 skipped 当成了成功。

### P4 — docs-only

删掉 `.ci/skip`，只改 `docs/`。`pass` 跑，`docs` 跑，`merge-recheck` 合法跳过；`kb-required` 绿，PR 可合（仍需 approval/up-to-date）。

### P5 — 分支过期

A 先合一个 PR；B 的 PR 不更新。期望：up-to-date 挡住；点 Update branch/rebase 后 check 在最新 SHA 上重跑。

### P6 — approval 失效

B approve；A 再 push 一个 commit。期望：旧 approval 失效；不能合，直到重新 approve。

### P7 — 自 approval

A 批自己的 PR。期望：不计入 required approval；仍不能合。

### P8 — bot bypass

用 deploy key 从本地直接推一个生成物 commit 到 `main`。期望：bot 成功；普通账号直接 push `main` 失败。若 deploy key 不能进 bypass，改用 GitHub App，记录差异。

### P9 — V2 decision

B 的分支加 `VLLM-ASC-10002`（同 root cause，不同 category）。C 应输出 mandatory pair，返回 2。加 `postmortems/decisions/VLLM-ASC-10002.yaml`，先写 `TODO`，仍应失败；填 `variant` + note + `content_sha256` 后，C 返回 0，`kb-required` 绿。

### P10 — same-case 字段冲突

A/B 改同一 case 的不同字段。C 返回 3；补 `same_case` 后返回 0。若两条改同一字段，C 继续返回 3，不能合。

### P11 — generated artifact

手改 `knowledge/_index.yaml`。C 返回 4，`kb-required` 红。撤销后恢复。

### P12 — merge queue（可选）

只有在仓库计划支持时做：

1. 开启 merge queue；
2. 两个 PR 入队；
3. 观察 `merge_group` 事件；
4. 确认 C 在 queue commit 上运行；
5. 失败时 PR 被移出队列。

如果 `merge_group` 的 base/head 不符合 C 的假设，记录并保留 up-to-date，不强行上 queue。

---

## 5. 证据

每个场景保存：

```text
artifacts/github-spike/<scenario>/
  pr.json
  checks.json
  ruleset.json
  merge.json
  notes.md
```

命令：

```bash
gh pr view <n> --json number,title,state,mergeStateStatus,reviewDecision,statusCheckRollup
gh pr checks <n>
gh api repos/<owner>/<repo>/commits/<sha>/check-runs
gh api repos/<owner>/<repo>/rulesets
```

`notes.md` 至少写：

- 预期；
- 实际；
- merge 按钮/API 结果；
- 失败时返回的错误；
- 是否 PASS/FAIL/UNTESTED。

---

## 6. 判定

- P1–P8 全部 PASS，才说明平台门可落地；
- P3 失败：先改聚合 job，不要上生产；
- P5/P6 失败：重新核对 GitHub 当前 ruleset 行为；
- P8 失败：改生成物重建方式（bot PR 或人工 post-merge），不要假设 bypass；
- P9/P10 失败：先修 C/decision，不要上生产；
- P12 失败：保留 up-to-date，不启用 merge queue。

任何一项没跑，写 **UNTESTED**，不写 PASS。

---

## 7. 清理

- 证据复制出来后再删除测试仓库；
- 不删除生产仓库的任何 branch/ruleset；
- 测试用的 deploy key / token 立即撤销；
- 报告里不出现 token、私钥、客户数据。

---

## 8. 生产启用前

测试仓库全部 PASS 后，才按 `10-platform-enforcement-spike-plan.md` 的结论改生产：

1. 去掉 workflow 级 `paths`；
2. 加 `kb-required`；
3. 只 required 这个 check；
4. 1 名非作者 approval + dismiss stale + up-to-date；
5. bot bypass；
6. 导出生产 ruleset 备份；
7. 先 reporting-only 观察，再切 blocking。
