"""Forward chaining (data-driven): fire rules whose premises hold until a fixed point is reached."""
from __future__ import annotations
from .expert_system import FiringRecord, Rule


def forward_chain(rules: list[Rule], facts: dict, scope: str, target: str = "global", max_iter: int = 20) -> tuple[dict, list[FiringRecord]]:
    wm = dict(facts)
    fired: set[str] = set()
    log: list[FiringRecord] = []
    rs = [r for r in rules if r.scope == scope]
    for _ in range(max_iter):
        changed = False
        for r in rs:
            if r.id in fired:
                continue
            ok = all(c.holds(wm) for c in r.premises)
            if ok:
                wm[r.conclusion[0]] = r.conclusion[1]
                fired.add(r.id)
                changed = True
            used = {c.fact: wm.get(c.fact) for c in r.premises}
            log.append(FiringRecord(r.id, r.name, r.scope, target, r.condition_text(), used, ok,
                                    r.recommendation if ok else "", r.explanation if ok else "Premises not satisfied"))
        if not changed:
            break
    # keep only the last evaluation per rule so the log is concise (final state of each rule)
    final: dict[str, FiringRecord] = {}
    for rec in log:
        if rec.rule_id not in final or rec.fired:
            final[rec.rule_id] = rec
    return wm, list(final.values())
