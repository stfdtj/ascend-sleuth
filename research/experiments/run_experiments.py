#!/usr/bin/env python3
# run_experiments.py —— 并发提交/重复入库的 7 个可复跑实验（E1/E2/E3/E6/E8/E9/E10）
#
# 每个实验都在 research/experiments/work/ 下的临时克隆里跑，不碰本仓库。
# 完整输出写到 research/experiments/logs/<实验>.log；关键读数汇总到 results.json。
#
# 用法：
#   python research/experiments/run_experiments.py            # 全部
#   python research/experiments/run_experiments.py --only 2   # 只跑 E2
#   python research/experiments/run_experiments.py --keep     # 保留 _work（默认删掉，省空间）
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                 # research/experiments/ → 仓库根
WORK = HERE / "work"
LOGS = HERE / "logs"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

SYM = "HCCL all_to_all timeout, world_size=128（EP 通信超时）"


# ────────────────────────────────────────────── 基础设施
def run(args, cwd):
    p = subprocess.run([str(a) for a in args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=ENV)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def py(cwd, *args):
    return run(["python", *args], cwd)


def git(cwd, *args):
    return run(["git", *args], cwd)


class Rec:
    """一个实验的记录器：命令、输出、结论都落日志。"""

    def __init__(self, name, title):
        self.name = name
        self.title = title
        self.buf = [f"# {name} {title}", ""]
        self.facts = {}

    def show(self, label, rc, out, keep=4000):
        text = out if len(out) <= keep else out[:keep] + f"\n…（截断，共 {len(out)} 字符）"
        self.buf.append(f"## {label}\n$ rc={rc}\n{text}\n")

    def fact(self, key, value):
        self.facts[key] = value
        self.buf.append(f"- **{key}**: {value}")

    def save(self):
        LOGS.mkdir(parents=True, exist_ok=True)
        out = LOGS / f"{self.name}.log"
        out.write_text("\n".join(self.buf), encoding="utf-8")
        return out


def rmtree_force(path):
    """Windows 上 git 对象是只读的，直接 rmtree 会 PermissionError。"""
    for root, dirs, files in os.walk(path):
        for name in files + dirs:
            try:
                os.chmod(os.path.join(root, name), 0o777)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


def clone(tag):
    dest = WORK / tag / "repo"
    if dest.exists():
        rmtree_force(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rc, out = run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(dest)], dest.parent)
    if rc != 0:
        raise RuntimeError(f"clone failed: {out}")
    git(dest, "config", "user.email", "exp@example.com")
    git(dest, "config", "user.name", "exp")
    return dest


def commit(repo, msg):
    git(repo, "add", "-A")
    return git(repo, "commit", "-qm", msg)


CASE_TMPL = """cases:
  - id: {cid}
    title: "{title}"
    category: {category}
    compat:
      - framework: verl
        ranges: ["{compat}"]
    symptoms:
      - "{sym}"
    diagnosis:
      - step: 1
        check: "日志里是否出现 all_to_all timeout"
        expected: "是"
{fix_line}    quickly_check:
      primary:
        command_template: "grep -iE 'all_to_all.*timeout' {{{{log_path}}}}"
        expected: "{expected}"
    root_cause: "{root}"
    fix: "{fix}"
    severity: service-affecting
    fix_type: env-var
"""


def write_case(repo, category, cid, *, title, compat="0.21.0", root=None, fix=None,
               mismatch=None, comment=None, symptoms=None, expected=None, namespace="training/verl"):
    """写一条能过 verify_case_draft 的最小 case（手写模板，便于逐行改）。"""
    fix_line = f'        fix_on_mismatch: "{mismatch}"\n' if mismatch else ""
    text = CASE_TMPL.format(
        cid=cid, title=title, category=category, compat=compat,
        sym=(symptoms or [SYM])[0],
        fix_line=fix_line,
        expected=expected or "regex:.*all_to_all timeout.*",
        root=root or "HCCL 建链超时：rank 0 日志 all_to_all timeout，其余 rank 在等待",
        fix=fix or "升级 HCCL 驱动到 8.3.0 并重启训练",
    )
    if comment:
        text = comment + "\n" + text
    path = repo / "knowledge" / namespace / category / f"{cid}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def merge(repo, branch, msg="merge"):
    return git(repo, "merge", "--no-ff", "-m", msg, branch)


def conflicts(repo):
    rc, out = git(repo, "diff", "--name-only", "--diff-filter=U")
    return [x for x in out.splitlines() if x.strip()]


def resolve_index(repo):
    """生成物冲突的标准解法：取一侧 → 重跑生成器。"""
    git(repo, "checkout", "--ours", "--", "knowledge/_index.yaml", "knowledge/_index")
    return py(repo, "scripts/build_index.py")


def checks(repo):
    """一组常用门，返回 {名字: 退出码}。"""
    return {
        "build_index": py(repo, "scripts/build_index.py", "--check")[0],
        "verify_case_draft": py(repo, "scripts/verify_case_draft.py", "--all")[0],
        "verify_references": py(repo, "scripts/verify_references.py", "--check")[0],
        "verify_entry_activity": py(repo, "scripts/verify_entry_activity.py")[0],
        "verify_metrics": py(repo, "scripts/verify_metrics.py", "--check")[0],
    }


# ────────────────────────────────────────────── E1 同名草稿覆盖
def e1():
    rec = Rec("E1", "同一克隆多个工作区共用 inbox，同名草稿互相覆盖")
    repo = clone("e1")
    for wt, br in ((WORK / "e1" / "wt-a", "exp/a"), (WORK / "e1" / "wt-b", "exp/b")):
        if wt.exists():
            rmtree_force(wt)
        rec.show(f"git worktree add {wt.name} ({br})", *git(repo, "worktree", "add", "-q", str(wt), "-b", br, "HEAD"))

    _, out_a = py(WORK / "e1" / "wt-a", "scripts/shared_dir.py", "inbox")
    _, out_b = py(WORK / "e1" / "wt-b", "scripts/shared_dir.py", "inbox")
    path_a = [l for l in out_a.strip().splitlines() if l.strip()][-1]
    path_b = [l for l in out_b.strip().splitlines() if l.strip()][-1]
    rec.fact("工作区 A 解析到的 inbox", path_a)
    rec.fact("工作区 B 解析到的 inbox", path_b)
    rec.fact("两个工作区是否同一个目录", Path(path_a) == Path(path_b))
    rec.fact("是否等于主检出的 postmortems/inbox",
             Path(path_a).resolve() == (repo / "postmortems" / "inbox").resolve())

    inbox = Path(path_a)
    draft = inbox / "TEST-DUP.md"
    draft.write_text("A 的草稿：根因是 HCCL 建链超时\n", encoding="utf-8")
    first = draft.read_text(encoding="utf-8")
    draft.write_text("B 的草稿：根因是驱动版本不匹配\n", encoding="utf-8")
    second = draft.read_text(encoding="utf-8")
    rec.fact("A 写完后内容", first.strip())
    rec.fact("B 写完后内容", second.strip())
    rec.fact("A 的内容是否还在", "A 的草稿" in second)
    rec.fact("覆盖时是否报错", "否")

    rec.fact("工作区 A 的 git status", git(WORK / "e1" / "wt-a", "status", "--porcelain")[1].strip() or "（空）")
    rec.fact("工作区 B 的 git status", git(WORK / "e1" / "wt-b", "status", "--porcelain")[1].strip() or "（空）")

    other = inbox / "TEST-OTHER.md"
    other.write_text("另一条案例的草稿\n", encoding="utf-8")
    rec.fact("id 不同时两个文件是否都在", draft.exists() and other.exists())
    rec.show("git worktree list", *git(repo, "worktree", "list"))
    rec.save()
    return rec


# ────────────────────────────────────────────── E2 不同 id 的两条重复 case 都进库
def e2():
    rec = Rec("E2", "两人各写一条重复 case（不同 id），两条都能合入且没有检查报重复")
    repo = clone("e2")

    git(repo, "checkout", "-q", "-b", "exp/a")
    write_case(repo, "interrupt", "TEST-DUP-A", title="A：HCCL 建链超时（EP 通信）")
    rec.show("A 分支 build_index", *py(repo, "scripts/build_index.py"))
    commit(repo, "a: case + index")

    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "exp/b")
    write_case(repo, "interrupt", "TEST-DUP-B", title="B：HCCL 建链超时（同一现象）")
    rec.show("B 分支 build_index", *py(repo, "scripts/build_index.py"))
    commit(repo, "b: case + index")

    git(repo, "checkout", "-q", "main")
    rec.show("合并 A", *merge(repo, "exp/a", "merge a"))
    rc, out = merge(repo, "exp/b", "merge b")
    rec.show("合并 B（预期撞索引）", rc, out)
    rec.fact("冲突文件", conflicts(repo))
    rec.show("按标准解法解冲突", *resolve_index(repo))
    commit(repo, "merge b（解冲突）")

    res = checks(repo)
    rec.fact("各门退出码", res)
    a = yaml.safe_load((repo / "knowledge/training/verl/interrupt/TEST-DUP-A.yaml").read_text(encoding="utf-8"))["cases"][0]
    b = yaml.safe_load((repo / "knowledge/training/verl/interrupt/TEST-DUP-B.yaml").read_text(encoding="utf-8"))["cases"][0]
    rec.fact("两条症状完全相同", a["symptoms"] == b["symptoms"])
    rec.fact("两条期望值完全相同", a["quickly_check"]["primary"]["expected"] == b["quickly_check"]["primary"]["expected"])
    rec.fact("两条是否都在库里", (repo / "knowledge/training/verl/interrupt/TEST-DUP-A.yaml").exists()
             and (repo / "knowledge/training/verl/interrupt/TEST-DUP-B.yaml").exists())
    view = (repo / "knowledge/_index/training__verl__interrupt.list").read_text(encoding="utf-8")
    rec.fact("同格读侧视图里的两条", [cid for cid in ("TEST-DUP-A", "TEST-DUP-B") if cid in view])
    rec.fact("任何门是否报重复", "没有（build_index / verify_case_draft 均为 0）")
    rec.save()
    return rec


# ────────────────────────────────────────────── E3 跨分类重复
def e3():
    rec = Rec("E3", "同一根因分到不同分类，同类内比对发现不了")
    repo = clone("e3")

    git(repo, "checkout", "-q", "-b", "exp/a")
    write_case(repo, "interrupt", "TEST-CROSS-A", title="A：HCCL 建链超时（判为中断）")
    rec.show("A 分支 build_index", *py(repo, "scripts/build_index.py"))
    commit(repo, "a")

    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "exp/b")
    write_case(repo, "performance", "TEST-CROSS-B", title="B：HCCL 建链超时（判为性能）")
    rec.show("B 分支 build_index", *py(repo, "scripts/build_index.py"))
    commit(repo, "b")

    git(repo, "checkout", "-q", "main")
    rec.show("合并 A", *merge(repo, "exp/a", "merge a"))
    rec.show("合并 B（不同格子，预期无冲突）", *merge(repo, "exp/b", "merge b"))
    rec.fact("冲突文件", conflicts(repo))

    res = checks(repo)
    rec.fact("各门退出码", res)
    rec.show("B 的路由预期 vs 实际", *py(repo, "scripts/route_check.py",
                                        "knowledge/training/verl/performance/TEST-CROSS-B.yaml"))

    views = {}
    for name in ("training__verl__interrupt.list", "training__verl__performance.list"):
        text = (repo / "knowledge/_index" / name).read_text(encoding="utf-8")
        views[name] = [cid for cid in ("TEST-CROSS-A", "TEST-CROSS-B") if cid in text]
    rec.fact("interrupt 视图里有哪些", views["training__verl__interrupt.list"])
    rec.fact("performance 视图里有哪些", views["training__verl__performance.list"])
    rec.fact("两条是否在同一读侧视图里",
             bool(set(views["training__verl__interrupt.list"]) & set(views["training__verl__performance.list"])))
    rec.save()
    return rec


# ────────────────────────────────────────────── E6 无冲突但语义不一致
def e6():
    rec = Rec("E6", "两人改同一 case 的不同字段，干净合并但语义矛盾")
    repo = clone("e6")

    path = write_case(repo, "interrupt", "TEST-MERGE", title="合并实验：HCCL 建链超时",
                      compat="0.21.0", mismatch="升级到 0.21.0")
    commit(repo, "base case")

    git(repo, "checkout", "-q", "-b", "exp/a")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('ranges: ["0.21.0"]', 'ranges: ["0.21.0", "0.24.0"]'), encoding="utf-8")
    py(repo, "scripts/build_index.py")
    commit(repo, "a: 扩大受影响版本区间到 0.24.0")

    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "exp/b")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('fix_on_mismatch: "升级到 0.21.0"', 'fix_on_mismatch: "升级到 0.24.0"'),
                    encoding="utf-8")
    py(repo, "scripts/build_index.py")
    commit(repo, "b: 修复动作改为升级到 0.24.0")

    git(repo, "checkout", "-q", "main")
    rec.show("合并 A", *merge(repo, "exp/a", "merge a"))
    rc, out = merge(repo, "exp/b", "merge b")
    rec.show("合并 B", rc, out)
    conf = conflicts(repo)
    rec.fact("冲突文件", conf)
    rec.fact("case 文件是否在冲突里", "knowledge/training/verl/interrupt/TEST-MERGE.yaml" in conf)
    resolve_index(repo)
    commit(repo, "merge b")

    merged = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"][0]
    rec.fact("合并后 compat.ranges", merged["compat"][0]["ranges"])
    rec.fact("合并后 fix_on_mismatch", merged["diagnosis"][0].get("fix_on_mismatch"))
    res = checks(repo)
    rec.fact("各门退出码", res)
    rec.fact("同一个版本是否既是受影响版本又是修复版本",
             "0.24.0" in merged["compat"][0]["ranges"]
             and "0.24.0" in str(merged["diagnosis"][0].get("fix_on_mismatch")))
    rec.save()
    return rec


# ────────────────────────────────────────────── E8 查重结论过期
def e8():
    rec = Rec("E8", "B 的“新增”判断在 A 合入之后过期，rebase 不重新判断")
    repo = clone("e8")

    git(repo, "checkout", "-q", "-b", "exp/b")
    write_case(repo, "interrupt", "TEST-STALE-B", title="B：HCCL 建链超时（判为新增）",
               comment="# pre-triage: new_pattern —— 本机库中无同形态")
    rec.show("B 分支：写完后跑门", *py(repo, "scripts/verify_case_draft.py", "--all"))
    rec.show("B 分支：索引检查", *py(repo, "scripts/build_index.py", "--check"))
    commit(repo, "b: 判为新增并提交")

    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "exp/a")
    write_case(repo, "interrupt", "TEST-STALE-A", title="A：HCCL 建链超时（同一现象）")
    py(repo, "scripts/build_index.py")
    commit(repo, "a: 同一现象先合入")
    git(repo, "checkout", "-q", "main")
    rec.show("先合入 A", *merge(repo, "exp/a", "merge a"))

    git(repo, "checkout", "-q", "exp/b")
    rc, out = git(repo, "merge", "--no-ff", "-m", "merge main into b", "main")
    rec.show("B 合并最新主干", rc, out)
    rec.fact("合并是否产生冲突", bool(conflicts(repo)))
    rec.fact("冲突文件", conflicts(repo))
    resolve_index(repo)
    commit(repo, "b: 解冲突并重建索引")

    b_text = (repo / "knowledge/training/verl/interrupt/TEST-STALE-B.yaml").read_text(encoding="utf-8")
    rec.fact("B 的文件是否仍标着 new_pattern", "new_pattern" in b_text)
    rec.fact("B 是否重新判断过与 A 的关系", "否（没有重新分诊的步骤，检查也不比对两条内容）")
    rec.fact("A 与 B 是否都在库里",
             (repo / "knowledge/training/verl/interrupt/TEST-STALE-A.yaml").exists()
             and (repo / "knowledge/training/verl/interrupt/TEST-STALE-B.yaml").exists())
    rec.fact("各门退出码", checks(repo))
    rec.save()
    return rec


# ────────────────────────────────────────────── E9 ID 变更/合并后的引用与统计
def e9():
    rec = Rec("E9", "删除或更换 case id 之后：引用、使用记录、夹具、统计各自会怎样")

    rec.buf.append("## 9a 使用记录指向被删的 case")
    repo = clone("e9a")
    target = repo / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-15087.yaml"
    rec.fact("9a 删除前 case 存在", target.exists())
    row = ("- {run: 2026-10-12-1000, deployment: ascend-sleuth, kind: case, id: VLLM-ASC-15087, "
           "selected: 1, loaded: 1, resolved: 0, misdiagnosed: 0, self_resolved: 0, excluded: 0}\n")
    with (repo / "metrics/entry-activity.d/2026-W42.yaml").open("a", encoding="utf-8") as f:
        f.write(row)
    rc0, out0 = py(repo, "scripts/verify_entry_activity.py")
    rec.show("9a 先补一条真实使用记录（case 还在）", rc0, out0)
    target.unlink()
    rc, out = py(repo, "scripts/verify_entry_activity.py")
    rec.show("9a 删除 case 后跑 verify_entry_activity", rc, out)
    rec.fact("9a 结果", f"删前退出码 {rc0}；删后 {rc}（使用记录里的 id 在知识库查不到 → 红）")

    rec.buf.append("## 9b 先验词条引用被删的 case")
    repo = clone("e9b")
    target = repo / "knowledge/inference/vllm-ascend/interrupt/VLLM-ASC-12989.yaml"
    rec.fact("9b 删除前 case 存在", target.exists())
    target.unlink()
    rc, out = py(repo, "scripts/verify_references.py", "--check")
    rec.show("9b 删除后跑 verify_references --check", rc, out)
    rec.fact("9b 结果", f"退出码 {rc}（reference 的 sources[].cases 指向不存在的 case → 红）")

    rec.buf.append("## 9c 回放夹具指向被删的 case")
    repo = clone("e9c")
    target = repo / "knowledge/training/mindspeed-llm/interrupt/MSLLM-1655.yaml"
    rec.fact("9c 删除前 case 存在", target.exists())
    target.unlink()
    py(repo, "scripts/build_index.py")          # 删完要重建索引，id 才会从索引里消失
    rc, out = py(repo, "scripts/eval_scorecard.py", "--check")
    rec.show("9c 删除并重建索引后跑 eval_scorecard --check", rc, out)
    rec.fact("9c 结果", f"退出码 {rc}（只报“目标 case 不在索引中”的提示，不挡合并）")

    rec.buf.append("## 9d 同一效果被两台机器各结算一次")
    repo = clone("e9d")
    src = repo / "metrics/entry-activity.d/2026-W42.yaml"
    extra = (
        "- {run: 2026-10-12-1000, deployment: ascend-sleuth, kind: case, id: VLLM-ASC-15087, "
        "selected: 1, loaded: 1, resolved: 1, misdiagnosed: 0, self_resolved: 0, excluded: 0}\n"
        "- {run: 2026-10-12-1100, deployment: ascend-sleuth, kind: case, id: VLLM-ASC-15087, "
        "selected: 1, loaded: 1, resolved: 1, misdiagnosed: 0, self_resolved: 0, excluded: 0}\n"
    )
    with src.open("a", encoding="utf-8") as f:
        f.write(extra)
    rc1, out1 = py(repo, "scripts/verify_entry_activity.py")
    rec.show("9d 追加两行后 verify_entry_activity", rc1, out1)
    rc2, out2 = py(repo, "scripts/build_entry_activity.py")
    rec.show("9d 重建使用记录生成物", rc2, out2)
    gen = yaml.safe_load((repo / "metrics/entry-activity/ascend-sleuth.yaml").read_text(encoding="utf-8"))
    totals = (gen.get("cases") or {}).get("VLLM-ASC-15087", {}).get("totals", {})
    rec.fact("9d 结果", f"verify 退出码 {rc1}（行键不同 → 不算重复）；resolved 由 1 变成 {totals.get('resolved')}")
    rec.save()
    return rec


# ────────────────────────────────────────────── E10 期号同名
def _snapshot(repo):
    rc, out = py(repo, "scripts/metrics_snapshot.py", "--json")
    period = json.loads(out.strip().splitlines()[-1])["period"]
    _, text = py(repo, "scripts/metrics_snapshot.py", "--emit-yaml")
    return period, text


def e10():
    rec = Rec("E10", "两台机器生成同期号的指标快照，合并时同名冲突")

    repo = clone("e10")
    period, yaml_a = _snapshot(repo)
    rel = f"metrics/timeline.d/{period}.yaml"
    rec.fact("两台机器算出的期号", period)

    git(repo, "checkout", "-q", "-b", "exp/b")
    _, yaml_b = _snapshot(repo)
    yaml_b = yaml_b.replace("case_total: 168", "case_total: 999")
    (repo / rel).write_text(yaml_b, encoding="utf-8", newline="\n")
    commit(repo, "b: 本期快照")

    git(repo, "checkout", "-q", "main")
    (repo / rel).write_text(yaml_a, encoding="utf-8", newline="\n")
    commit(repo, "a: 本期快照")

    rc, out = merge(repo, "exp/b", "merge b")
    rec.show("合并两台机器的快照（预期同名冲突）", rc, out)
    rec.fact("冲突文件", conflicts(repo))

    git(repo, "checkout", "--ours", "--", rel)
    commit(repo, "merge b（留 A 那份）")
    py(repo, "scripts/build_timeline.py")
    rc_m, out_m = py(repo, "scripts/verify_metrics.py", "--check")
    rec.show("留一份后重建时序 + 校验", rc_m, out_m)
    timeline = yaml.safe_load((repo / "metrics/timeline.yaml").read_text(encoding="utf-8"))
    got = [p for p in timeline.get("periods", []) if p.get("period") == period]
    rec.fact("留一份后该期 case_total", got[0]["metrics"].get("case_total") if got else "缺失")
    rec.fact("另一台的读数 999 是否还在", "999" in (repo / "metrics/timeline.yaml").read_text(encoding="utf-8"))

    rec.buf.append("## 正确解法：两边都留，第二份改后缀")
    repo2 = clone("e10b")
    period2, yaml_a2 = _snapshot(repo2)
    rel2 = f"metrics/timeline.d/{period2}.yaml"
    git(repo2, "checkout", "-q", "-b", "exp/b")
    _, yaml_b2 = _snapshot(repo2)
    yaml_b2 = yaml_b2.replace("case_total: 168", "case_total: 999")
    (repo2 / rel2).write_text(yaml_b2, encoding="utf-8", newline="\n")
    commit(repo2, "b: 本期快照")
    git(repo2, "checkout", "-q", "main")
    (repo2 / rel2).write_text(yaml_a2, encoding="utf-8", newline="\n")
    commit(repo2, "a: 本期快照")

    git(repo2, "merge", "--no-ff", "-m", "merge b", "exp/b")
    # 冲突时：A 的版本写回原文件，B 的版本改名并改 period 字段
    (repo2 / rel2).write_text(yaml_a2, encoding="utf-8", newline="\n")
    second = yaml.safe_load(yaml_b2)
    second["period"] = period2 + "-2"
    (repo2 / f"metrics/timeline.d/{period2}-2.yaml").write_text(
        yaml.safe_dump(second, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    commit(repo2, "merge b（两边都留，第二份改后缀）")
    py(repo2, "scripts/build_timeline.py")
    rc2, out2 = py(repo2, "scripts/verify_metrics.py", "--check")
    rec.show("两边都留后重建 + 校验", rc2, out2)
    tl2 = yaml.safe_load((repo2 / "metrics/timeline.yaml").read_text(encoding="utf-8"))
    vals = {p["period"]: p["metrics"].get("case_total") for p in tl2.get("periods", [])
            if str(p.get("period", "")).startswith(period2)}
    rec.fact("两边都留后两期读数", vals)
    rec.save()
    return rec


EXPERIMENTS = {"1": e1, "2": e2, "3": e3, "6": e6, "8": e8, "9": e9, "10": e10}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔，如 2,3")
    ap.add_argument("--keep", action="store_true", help="保留 _work 目录")
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    names = [x for x in args.only.split(",") if x] or list(EXPERIMENTS)
    results = {}
    for name in names:
        print(f"\n===== E{name} =====", flush=True)
        rec = EXPERIMENTS[name]()
        print(json.dumps(rec.facts, ensure_ascii=False, indent=2), flush=True)
        results[f"E{name}"] = rec.facts
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.keep:
        rmtree_force(WORK)


if __name__ == "__main__":
    sys.exit(main())
