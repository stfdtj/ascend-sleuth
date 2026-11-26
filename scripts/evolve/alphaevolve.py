"""Quality-diversity selection over trusted evaluator scores."""
from bisect import bisect_right
from math import isfinite
from random import Random


class AlphaEvolvePolicy:
    id = "alphaevolve"

    def __init__(self, objective="objective", correctness="correct", dimensions=None, seed=0):
        self.objective = objective
        self.correctness = correctness
        self.dimensions = {} if dimensions is None else dict(dimensions)
        self.seed = int(seed)
        for edges in self.dimensions.values():
            if sorted(set(edges)) != list(edges) or not all(map(isfinite, edges)):
                raise ValueError("feature thresholds must be finite and strictly increasing")

    def configuration(self):
        return dict(objective=self.objective, correctness=self.correctness,
                    dimensions=self.dimensions, seed=self.seed)

    def elites(self, candidates, samples):
        cells = {}
        required = set(samples) | {self.correctness, self.objective} | self.dimensions.keys()
        for candidate in candidates:
            scores = candidate.scores
            if candidate.status != "evaluated" or not required.issubset(scores):
                continue
            if scores[self.correctness] != 1 or not all(isfinite(scores[k]) for k in required):
                continue
            cell = tuple(bisect_right(edges, scores[name]) for name, edges in self.dimensions.items())
            incumbent = cells.get(cell)
            if incumbent is None or scores[self.objective] > incumbent.scores[self.objective]:
                cells[cell] = candidate
        return list(cells.values())

    def choose(self, candidates, samples, reflected=()):
        return max(self.elites(candidates, samples), key=lambda c: c.scores[self.objective], default=None)

    def select_parents(self, candidates, samples, reflected):
        pool = self.elites(candidates, samples)
        rng = Random(f"{self.seed}/{len(reflected)}")
        rng.shuffle(pool)
        return (pool[0], pool[1:3]) if pool else (None, [])
