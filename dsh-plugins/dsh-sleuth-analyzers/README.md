# dsh-sleuth-analyzers（八个外部分析器的接入层）

一个包、八行开关、一个工具。分析器实现按 `tools/<name>/` 分发；本包只放入口、契约与约束表。

**现状**：接入层可用，分析器实现尚未随包分发。调用会返回 `blocked: analyzer-not-installed`——这是如实返回，不是故障。

## 装

```
node scripts/panel_install.js --spec "<本目录绝对路径>"
```

装完重启 DSH Desktop。设置页的「分析器」一项填状态目录（不填则落系统临时目录 `sleuth-analyzers/traces/evidence`）。

## 验证

1. 工具在不在：新会话的工具目录里应有 `sleuth_analyze`。
2. 状态查询：`curl http://127.0.0.1:<port>/sleuth-analyzers/api/status` 返回 `analyzers` 八行（enabled / installed）与 python 解析结果。
3. 关掉 `analyzers-run` 那一行，工具消失；再打开，工具回来——这验证「关一行 = 该能力不存在」。
4. 调一次：`sleuth_analyze(analyzer: "ibmc_analyzer", inputs: "<某个绝对路径>")`，预期 `ok:false, reason: analyzer-not-installed`。

## 目录

```
package.json        包清单
cordis.patch.yml    八行开关 + 工具行 + 设置行
index.js            工具注册、python 解析、预算、截断、落盘
constraints.yaml    约束表（C1–C8）：不装依赖、只写状态目录、输入只读、不代做现场动作……
tools/<name>/       分析器实现（未分发），入口固定为 run.py
```

`tools/<name>/run.py` 的接口固定：`--inputs <JSON 数组> --out-dir <目录> --ab <A|B> --purpose <一句话>`，在 `--out-dir` 写 `result.json`（字段见下）。

## 结果契约

```json
{
  "status": "ok|partial|blocked|failed",
  "summary": "≤500 字",
  "findings": [{"claim": "...", "evidence": "...", "kind": "fact|candidate"}],
  "missing": ["..."],
  "artifacts": ["..."],
  "analyzer_version": "..."
}
```

`summary` 必须先写覆盖范围与失败项，不能因为截断丢掉缺项。

## 还没做

- 八个分析器的实现与 `tools/` 目录（下一步：按分析器逐个迁入，配 `upstream-sources/` 与 `overrides/`）。
- 设置页的客户端半边（现在只有状态查询路由，没有界面）。
- 沙箱验证：工具在主进程里 spawn python，`workspace-write` 档下能否启动未验证。

## 本分支在对照实验里是什么（臂 B）

本分支相对 `main` 只多三样：这个插件包、`skills/diagnose/SKILL.md` 步骤 5 的一句转接、`skills/diagnose/references/analyzer-dispatch.md`。知识库与其它流程不动。对照方案见 [`proposals/analyzer-arms-experiment.md`](../../proposals/analyzer-arms-experiment.md)。

**agent 多能做什么**：在步骤 5 判定「手上有整包数据」时调一次 `sleuth_analyze(analyzer, inputs, purpose, ab, session_id)`，拿到结构化摘要与证据文件；选型、退化、记账规则都在 `analyzer-dispatch.md`。

**产出多什么**：每题多一个 `traces/evidence/<session>/tool-runs/<call_id>/`（`invocation.json`、`stdout.log`、`stderr.log`、`result.json`），trace 里多一条 `run_check`（`check: analyzer_run`）。

**验收时看四点**：① 该调的时候是否调了；② 分析器选得对不对；③ 返回的发现有没有被写进结论（还是只贴了个路径）；④ 失败时是否退化回原路径、有没有被记成「已排除」。

**现状（影响实验）**：八个分析器的实现还没随包分发，调用一律返回 `analyzer-not-installed`，所以**臂 B 现在跑出来的结果等于基线**。本分支当前可验收的只有接线：装包 → 工具出现 → 调一次看返回 → 关一行看工具消失。效果对比要等第一个分析器（建议 `issue-analyzer`）随包之后再跑。

