import unittest
from types import SimpleNamespace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from evolve.alphaevolve import AlphaEvolvePolicy


class QualityDiversityTest(unittest.TestCase):
    def test_replacement_constraints_and_sampling(self):
        policy = AlphaEvolvePolicy(dimensions={"length": [10]})
        def candidate(name, objective, length, correct=1):
            return SimpleNamespace(id=name, status="evaluated",
                                   scores=dict(objective=objective, length=length, correct=correct))
        a = candidate("a", 1, 4)
        b = candidate("b", 2, 5)
        c = candidate("c", 3, 10)
        invalid = candidate("invalid", 100, 11, 0)
        population = [a, b, c, invalid]
        self.assertEqual(policy.elites(population, []), [b, c])
        self.assertIs(policy.choose(population, []), c)
        first = policy.select_parents(population, [], ["b"])
        self.assertEqual(first, policy.select_parents(population, [], ["b"]))
        self.assertEqual({first[0].id, first[1][0].id}, {"b", "c"})

    def test_resume_pending_mutation_and_budget(self):
        import tempfile
        from evolve.proposal_engine import ProposalArchive, ProposalEngine
        from evolve.loops.proposal import ProposalLoop
        from test_proposal_engine import skill_draft
        with tempfile.TemporaryDirectory() as directory:
            engine = ProposalEngine(ProposalArchive(Path(directory) / "archive.jsonl"))
            policy = AlphaEvolvePolicy()
            loop = ProposalLoop(engine, ["objective"], policy=policy, max_evaluations=2)
            loop.apply(loop.next_action(), {"draft": skill_draft()})
            loop.apply(loop.next_action(), {"scores": {"correct": 1, "objective": 1}})
            action = loop.next_action()
            restored = ProposalLoop.from_dict(loop.to_dict(), policy=policy)
            self.assertEqual(restored.next_action(), action)
            restored.apply(action, {"draft": skill_draft(diff="+ changed")})
            self.assertEqual(restored.engine.proposals[1].parent, action["parent"])
            restored.apply(restored.next_action(), {"scores": {"correct": 0, "objective": 9}})
            self.assertEqual(restored.next_action()["reason"], "evaluation_budget")
            self.assertEqual(restored.result()["selected"]["id"], action["parent"])

    def test_cli_uses_configured_metrics(self):
        import json
        import tempfile
        from test_cli import run_cli
        from test_proposal_engine import skill_draft
        with tempfile.TemporaryDirectory() as directory:
            scenario = Path(directory) / "scenario.json"
            scenario.write_text(json.dumps({
                "target_kind": "skill", "target_component": "diagnose.knowledge_usage",
                "samples": ["speed"], "alphaevolve": {"objective": "speed", "dimensions": {"size": [10]}},
                "candidates": [{"draft": skill_draft(), "scores": {"speed": speed, "size": 4, "correct": valid}}
                               for speed, valid in [(1, 1), (3, 0)]],
            }), encoding="utf8")
            result = run_cli("experiment", "search", "--root", directory, "--scenario", str(scenario),
                             "--policy", "alphaevolve")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["selected"]["scores"]["speed"], 1)
