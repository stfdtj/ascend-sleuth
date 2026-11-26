"""Offline script-search fixture. Run with python experiments/alphaevolve_demo.py."""
import json
import sys
import tempfile
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evolve.alphaevolve import AlphaEvolvePolicy
from evolve.proposal_engine import ProposalArchive, ProposalEngine, GepaPolicy
from evolve.loops.proposal import ProposalLoop

# Execute only these immutable fixture expressions. Cost counts arithmetic operations.
FORMS = {
    "sum(range(n))": lambda n: n,
    "sum(range(n + 1))": lambda n: n + 1,
    "n * (n + 1) // 2": lambda n: 3,
}
TRAIN = (3, 8, 15)
HOLDOUT = (0, 1, 57)


def evaluate(source, inputs):
    cost = FORMS[source]
    correct = all(eval(source, {"__builtins__": {}, "sum": sum, "range": range}, {"n": n})
                  == sum(range(1, n + 1)) for n in inputs)
    return {"correct": int(correct), "objective": 1 / sum(cost(n) for n in inputs),
            "size": len(source)}


def run(directory, arm, seed=None, budget=3):
    start = perf_counter()
    engine = ProposalEngine(ProposalArchive(directory / (arm + ".jsonl")))
    policy = GepaPolicy() if arm.endswith("gepa") else AlphaEvolvePolicy(dimensions={"size": [17]})
    loop = ProposalLoop(engine, ["correct", "objective"], max_evaluations=budget, policy=policy)
    if seed is not None:
        imported = engine.add(seed["draft"])
        if imported.status != "candidate":
            raise ValueError(imported.errors)
    sources = list(FORMS)
    original = sources[0]
    calls = 0
    first_optimum = None
    while True:
        action = loop.next_action()
        if action["kind"] == "stop":
            break
        if action["kind"] == "reflect":
            parent = loop.parent_proposal()
            base = parent.artifact["diff"] if parent else original
            source = sources[1] if arm == "repair" else sources[-1]
            if base not in FORMS:
                raise ValueError("unexpected parent expression")
            calls += 1
            loop.apply(action, {"draft": {"target_kind": "tooling", "target_component": "tooling",
                        "summary": "sum integers", "change": {"files": ["scripts/sum_task.py"], "diff": source},
                        "expected": "triangular sum", "risk": "fixture", "rollback": "restore expression"}})
        else:
            proposal = loop.proposal(action["proposal_id"])
            scores = evaluate(proposal.artifact["diff"], TRAIN)
            if first_optimum is None and proposal.artifact["diff"] == sources[-1]:
                first_optimum = loop.evaluations + 1
            if isinstance(policy, GepaPolicy):
                scores.pop("size")
            loop.apply(action, {"scores": scores})
            if arm == "repair":
                break
    chosen = loop.result()["selected"]
    if chosen is None:
        raise ValueError([p.errors for p in engine.proposals])
    source = chosen["artifact"]["diff"]
    variants = sorted({p.artifact["diff"] for p in engine.proposals})
    return {
        "draft": loop.proposal(chosen["id"]).draft,
        "arm": arm, "script": source, "variants": variants, "diversity": len(variants),
        "evaluations": loop.evaluations, "first_optimum": first_optimum,
        "mock_calls": calls, "tokens": 0, "seconds": perf_counter() - start,
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp:
        for arm in ("repair", "alphaevolve", "repair-alphaevolve", "repair-gepa"):
            root = Path(temp) / arm
            root.mkdir()
            if arm.startswith("repair-"):
                repair = run(root, "repair", budget=1)
                result = run(root, arm, seed=repair, budget=2)
                if result["first_optimum"] is not None:
                    result["first_optimum"] += repair["evaluations"]
                for key in ("evaluations", "mock_calls", "seconds"):
                    result[key] += repair[key]
                result["diversity"] = len(set(repair["variants"] + result["variants"]))
            else:
                result = run(root, arm)
            result["heldout"] = evaluate(result["script"], HOLDOUT)
            del result["draft"], result["variants"]
            print(json.dumps(result))
