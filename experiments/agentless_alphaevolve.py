"""Run the pinned offline Agentless example and optimize its validated output."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evolve.alphaevolve import AlphaEvolvePolicy
from evolve.loops.proposal import ProposalLoop
from evolve.proposal_engine import ProposalArchive, ProposalEngine

BASE = "f848f6a7c8738decb36126d683b84bcc57195dcd"
TARGET = "scripts/analyzers/ibmc_analyzer/run.py"
BEFORE = "(line.strip() for line in stream if line.strip())"
AFTER = "(line for line in map(str.strip, stream) if line)"


def run(repo, out):
    """Use a disposable checkout and the reference revision's evaluator."""
    work = out / "repo"
    subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", work, BASE], check=True)
    try:
        driver = """
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from evolve.algorithms.agentless import run_trial
root = Path.cwd()
out = Path(sys.argv[1])
if run_trial(root, out):
    raise SystemExit(1)
raise SystemExit(run_trial(root, out, next(root.rglob('ibmc-presence-response.md')), attempt=None))
"""
        trial = out / "repair"
        subprocess.run([sys.executable, "-X", "utf8", "-c", driver, trial], cwd=work, check=True)
        attempt, = trial.glob("attempt-*")
        result = json.loads((attempt / "result.json").read_text(encoding="utf8"))
        candidate = json.loads((attempt / "candidate.json").read_text(encoding="utf8"))
        if (result["decision"] != "pass" or candidate["base_rev"] != BASE
                or candidate["file"] != TARGET):
            raise ValueError("expected validated candidate for pinned target")
        path = work / TARGET
        source = path.read_text(encoding="utf8")
        if source.count(candidate["old_text"]) != 1:
            raise ValueError("ambiguous repair")
        repaired = source.replace(candidate["old_text"], candidate["new_text"])
        if repaired.count(BEFORE) != 1:
            raise ValueError("unexpected repaired implementation")

        engine = ProposalEngine(ProposalArchive(out / "archive.jsonl"))
        loop = ProposalLoop(engine, ["objective"], policy=AlphaEvolvePolicy(), max_evaluations=2)
        while (action := loop.next_action())["kind"] != "stop":
            if action["kind"] == "reflect":
                parent = loop.parent_proposal()
                program = parent.artifact["diff"].replace(BEFORE, AFTER) if parent else repaired
                loop.apply(action, {"draft": dict(target_kind="tooling", target_component=candidate["region"],
                           summary="Reduce strip calls per nonempty line", expected="One strip per line",
                           risk="Header interpretation", rollback="Restore parent source",
                           evidence=[candidate["candidate_id"]], change=dict(files=[TARGET], diff=program))})
                continue
            proposal = loop.proposal(action["proposal_id"])
            program = proposal.artifact["diff"]
            path.write_text(program, encoding="utf8")
            probe = subprocess.check_output([sys.executable, "-X", "utf8",
                "scripts/evolve/evaluations/ibmc_presence.py"], cwd=work, encoding="utf8")
            samples = json.loads(probe)
            regression = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest",
                                         "tests.test_analyzers"], cwd=work)
            correct = regression.returncode == 0 and samples.keys() == result["samples"].keys() and all(
                s["pass"] for s in samples.values())
            loop.apply(action, {"scores": dict(correct=int(correct), objective=1 if AFTER in program else 0.5)})
        selected = loop.result()["selected"]
        print(json.dumps(dict(repair=candidate["candidate_id"], repair_tests=result["passed"],
                              selected=selected["id"], scores=selected["scores"], parent=selected["parent"])))
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", work], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path, help="Repository containing the pinned Agentless commit")
    with tempfile.TemporaryDirectory() as directory:
        run(parser.parse_args().repo.resolve(), Path(directory))
