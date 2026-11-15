"""Backtracking solver with MRV + importance tie-break, value-ordering heuristic and forward checking."""
from __future__ import annotations
import time
from collections import Counter
from dataclasses import dataclass, field
from .csp import CSP


@dataclass
class CSPResult:
    solution: dict | None
    nodes: int = 0
    backtracks: int = 0
    pruned_values: int = 0
    seconds: float = 0.0
    failed_constraints: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    exhausted: bool = True

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def solve(csp: CSP, node_limit: int = 200_000, trace_limit: int = 80) -> CSPResult:
    t0 = time.perf_counter()
    res = CSPResult(None)
    fails: Counter = Counter()
    domains = {v: list(d) for v, d in csp.variables.items()}
    # unary constraints / node consistency
    for c in csp.constraints:
        if len(c.scope) == 1:
            v = c.scope[0]
            domains[v] = [x for x in domains[v] if c.check({v: x})]
    if any(not d for d in domains.values()):
        res.failed_constraints = {"empty_domain": 1}
        res.seconds = time.perf_counter() - t0
        return res

    def select(assign: dict, doms: dict) -> str:
        un = [v for v in doms if v not in assign]
        return min(un, key=lambda v: (len(doms[v]), -csp.priority.get(v, 0.0)))   # MRV, then highest importance

    def ordered(v: str, doms: dict) -> list:
        key = csp.value_key.get(v)
        return sorted(doms[v], key=key) if key else list(doms[v])

    def forward_check(assign: dict, doms: dict) -> dict | None:
        new = {k: list(x) for k, x in doms.items()}
        for c in csp.constraints:
            if c.partial and not c.partial(assign, new):
                fails[c.name + " (bounds)"] += 1
                return None
        for v in new:
            if v in assign:
                continue
            keep = []
            for x in new[v]:
                trial = {**assign, v: x}
                ok = True
                for c in csp.constraints:
                    if v in c.scope and all(s in trial for s in c.scope) and not c.check(trial):
                        fails[c.name] += 1
                        ok = False
                        break
                    if ok and c.partial and v in c.scope and not c.partial(trial, new):
                        fails[c.name + " (bounds)"] += 1
                        ok = False
                        break
                if ok:
                    keep.append(x)
                else:
                    res.pruned_values += 1
            if not keep:
                return None
            new[v] = keep
        return new

    def bt(assign: dict, doms: dict) -> dict | None:
        if len(assign) == len(doms):
            return dict(assign)
        v = select(assign, doms)
        for x in ordered(v, doms):
            res.nodes += 1
            if res.nodes > node_limit:
                res.exhausted = False
                return None
            assign[v] = x
            ok, bad = csp.consistent(assign, v)
            if len(res.trace) < trace_limit:
                res.trace.append({"var": v, "value": x, "consistent": ok, "violated": bad, "depth": len(assign)})
            if ok:
                nd = forward_check(assign, doms)
                if nd is not None:
                    r = bt(assign, nd)
                    if r is not None:
                        return r
            else:
                fails[bad] += 1
            del assign[v]
            res.backtracks += 1
        return None

    res.solution = bt({}, domains)
    res.failed_constraints = dict(fails.most_common(8))
    res.seconds = time.perf_counter() - t0
    return res
