import copy
import json
import random
import unittest
from collections import deque
from pathlib import Path
from foundry.core import manifest, rholang, simulate, parse, load_spec, SpecError, MAX_VERSION

ROOT=Path(__file__).resolve().parents[1]
def spec(name="escrow"):
    return load_spec((ROOT/"examples"/(name+".json")).read_text())

def oracle(raw):
    """Deliberately separate forward search over resource vectors."""
    p=parse(raw); reached={p.initial}; q=deque([p.initial]); edges={}
    while q:
        s=q.popleft()
        for a in p.actions:
            if not all(g.holds(s) for g in a.guards):continue
            t=tuple(s[i]+a.delta[i] for i in range(len(s)))
            if any(t[i]<0 or t[i]>p.caps[i] for i in range(len(t))):continue
            assert all(g.holds(t) for g in p.invariants)
            edges[s,a.name]=t
            if t not in reached:reached.add(t);q.append(t)
    goals={}
    for g in p.goals:
        for s in reached:
            q=deque([(s,())]);seen={s}
            while q:
                t,path=q.popleft()
                if all(k.holds(t) for k in g.predicates):
                    if path:goals[g.role,s,g.name]=(t,path)
                    break
                for a in sorted(g.actions):
                    u=edges.get((t,a))
                    if u is not None and u not in seen:
                        q.append((u,path+(a,)));seen.add(u)
    return reached,edges,goals

class Tests(unittest.TestCase):
    def compare(self,raw):
        m=manifest(raw);p=parse(raw);states=[tuple(s) for s in m["states"]]
        reached,edges,goals=oracle(raw)
        self.assertEqual(set(states),reached)
        self.assertEqual({(states[s],a):states[t] for s,a,t in m["edges"]},edges)
        expected=dict(goals)
        for (s,a),t in edges.items():
            for role in next(x.roles for x in p.actions if x.name==a):
                expected[role,s,a]=(t,(a,))
        self.assertEqual({(r["role"],states[r["state"]],r["operation"]):(states[r["target"]],tuple(r["path"])) for r in m["rules"]},expected)
    def test_escrow(self):
        raw=spec();self.compare(raw);m=manifest(raw)
        settle=next(r for r in m["rules"] if r["state"]==0 and r["operation"]=="settle")
        self.assertEqual(settle["path"],["fund","prepare","deliver","approve","release"])
        self.assertEqual(simulate(m,0,0,"settler","settle",0),("OK",settle["target"],1))
        self.assertEqual(simulate(m,0,0,"buyer","settle",0),("DENIED",0,0))
        self.assertEqual(simulate(m,settle["target"],1,"settler","settle",0),("STALE",settle["target"],1))
    def test_reservation(self):
        self.compare(spec("reservation"))
    def test_exhaustive_admission(self):
        for n in ["escrow","reservation"]:
            raw=spec(n);m=manifest(raw);rules={(r["role"],r["state"],r["operation"]):r for r in m["rules"]}
            ops=[a["name"] for a in raw["actions"]]+[g["name"] for g in raw["goals"]]+["missing"]
            for s in range(len(m["states"])):
                for role in raw["roles"]:
                    for op in ops:
                        r=rules.get((role,s,op))
                        self.assertEqual(simulate(m,s,9,role,op,9),("OK",r["target"],10) if r else ("DENIED",s,9))
                        self.assertEqual(simulate(m,s,9,role,op,8),("STALE",s,9))
                        self.assertEqual(simulate(m,s,MAX_VERSION,role,op,MAX_VERSION),("EXHAUSTED",s,MAX_VERSION))
                    self.assertEqual(simulate(m,s,9,role,"inspect",0),("STATE",s,9))
    def test_randomized_shortest_paths(self):
        rng=random.Random(912)
        for i in range(150):
            raw=spec("reservation");n=rng.randint(1,10)
            for r in raw["resources"].values():r["capacity"]=n
            raw["resources"]["free"]["initial"]=n
            raw["invariants"][0]["rhs"]=n
            raw["goals"][0]["predicates"][0]["rhs"]=rng.randint(1,n)
            if rng.random()<.5:raw["goals"][0]["actions"].append("cancel")
            self.compare(raw)
    def test_authority_escalation_refused(self):
        raw=spec();raw["goals"][0]["role"]="buyer"
        with self.assertRaisesRegex(SpecError,"escalate"):manifest(raw)
    def test_invariant_violation_refused(self):
        raw=spec();raw["actions"][0]["delta"]["escrow"]=3
        with self.assertRaisesRegex(SpecError,"invariant violation"):manifest(raw)
    def test_no_authority_laundering(self):
        raw=spec();raw["actions"][3]["roles"]=["buyer"]
        with self.assertRaises(SpecError):manifest(raw)
    def test_unsafe_initial_refused(self):
        raw=spec();raw["resources"]["cash"]["initial"]=3
        with self.assertRaises(SpecError):manifest(raw)
    def test_duplicate_and_injection_refused(self):
        with self.assertRaises(SpecError):load_spec('{"a":1,"a":2}')
        raw=spec();raw["roles"][0]='evil")'
        with self.assertRaises(SpecError):manifest(raw)
    def test_bounds_and_types(self):
        raw=spec();raw["resources"]["cash"]["capacity"]=True
        with self.assertRaises(SpecError):manifest(raw)
        raw=spec("reservation");n=100
        for r in raw["resources"].values():r["capacity"]=n
        raw["resources"]["free"]["initial"]=n;raw["invariants"][0]["rhs"]=n
        with self.assertRaisesRegex(SpecError,"state budget"):manifest(raw)
    def test_deterministic(self):
        raw=spec();self.assertEqual(manifest(raw),manifest(copy.deepcopy(raw)))
        self.assertEqual(rholang(raw),rholang(copy.deepcopy(raw)))
        self.assertEqual(rholang(raw).count('bundle+{'),len(raw["roles"]))
        self.assertNotIn('state!(*state)',rholang(raw))
    def test_unreachable_goal(self):
        raw=spec();raw["goals"][0]["actions"]=["release"]
        m=manifest(raw);self.assertEqual(simulate(m,0,0,"settler","settle",0),("DENIED",0,0))
    def test_deny_does_not_change_version(self):
        m=manifest(spec());self.assertEqual(simulate(m,0,3,"buyer","release",3),("DENIED",0,3))
        self.assertEqual(simulate(m,0,3,"buyer","fund",True),("STALE",0,3))

if __name__=="__main__":unittest.main()
