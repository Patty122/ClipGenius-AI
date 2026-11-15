"""Backward chaining (goal-driven): prove a goal from facts, recursively proving rule premises."""
from __future__ import annotations
from .expert_system import Cond, Rule


def prove(goal: str, rules: list[Rule], facts: dict, _stack: tuple = (), want=True) -> dict:
    """Returns {goal, proved, via, children[]}. A goal is proved if it is a known fact with the wanted value,
    or if some rule concluding it has all premises provable (premises with comparison ops are tested on facts,
    premises that are themselves derivable are proven recursively)."""
    if goal in facts and facts[goal] == want:
        return {"goal": goal, "proved": True, "via": "fact", "children": []}
    if goal in _stack:
        return {"goal": goal, "proved": False, "via": "cycle", "children": []}
    attempts = []
    for r in [r for r in rules if r.conclusion[0] == goal and r.conclusion[1] == want]:
        children, all_ok = [], True
        for c in r.premises:
            if c.holds(facts):
                children.append({"goal": c.text(), "proved": True, "via": "fact", "children": []})
                continue
            if c.op == "truthy" and any(x.conclusion[0] == c.fact for x in rules):
                sub = prove(c.fact, rules, facts, _stack + (goal,))
                children.append(sub)
                if not sub["proved"]:
                    all_ok = False
            else:
                children.append({"goal": c.text(), "proved": False, "via": "fact", "children": []})
                all_ok = False
        attempts.append((r, children, all_ok))
        if all_ok:
            return {"goal": goal, "proved": True, "via": f"{r.id}: {r.name}", "children": children}
    if attempts:
        r, children, _ = attempts[0]
        return {"goal": goal, "proved": False, "via": f"{r.id}: {r.name}", "children": children}
    return {"goal": goal, "proved": False, "via": "no rule or fact", "children": []}


def unmet(tree: dict) -> list[str]:
    """Leaf premises that failed -- explains why a goal could not be proved."""
    if tree["proved"]:
        return []
    if not tree["children"]:
        return [tree["goal"]]
    out: list[str] = []
    for c in tree["children"]:
        out += unmet(c)
    return out
