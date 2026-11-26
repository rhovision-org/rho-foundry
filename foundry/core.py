"""Compile a finite, declarative resource protocol into an atomic capability machine."""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import re

MAX_STATES = 2048
MAX_EDGES = 24000
MAX_RULES = 24000
MAX_PLAN_STEPS = 1000000
MAX_VERSION = 2147483647
NAME = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")

class SpecError(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise SpecError(message)

def fields(value, expected, where):
    require(type(value) is dict and set(value) == set(expected), "invalid fields: " + where)

def integer(x, lo, hi):
    return type(x) is int and lo <= x <= hi

def name(x):
    return type(x) is str and NAME.fullmatch(x) is not None

def names(xs, limit, where):
    require(type(xs) is list and 0 < len(xs) <= limit and all(name(x) for x in xs), "invalid names: " + where)
    require(len(xs) == len(set(xs)), "duplicate names: " + where)
    return tuple(xs)

def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()

def load_spec(text):
    require(len(text.encode()) <= 262144, "spec byte limit")
    def no_duplicates(pairs):
        result = {}
        for k,v in pairs:
            require(k not in result, "duplicate JSON field: " + k)
            result[k] = v
        return result
    return json.loads(text, object_pairs_hook=no_duplicates)

@dataclass(frozen=True)
class Predicate:
    weights: tuple
    op: str
    rhs: int
    def holds(self, state):
        n = sum(a*b for a,b in zip(self.weights,state))
        return n == self.rhs if self.op == "eq" else n <= self.rhs if self.op == "le" else n >= self.rhs

@dataclass(frozen=True)
class Action:
    name: str
    roles: tuple
    guards: tuple
    delta: tuple

@dataclass(frozen=True)
class Goal:
    name: str
    role: str
    actions: tuple
    predicates: tuple

@dataclass(frozen=True)
class Protocol:
    name: str
    resources: tuple
    roles: tuple
    initial: tuple
    caps: tuple
    invariants: tuple
    actions: tuple
    goals: tuple

def parse(raw):
    fields(raw, ["name","resources","roles","invariants","actions","goals"], "protocol")
    require(name(raw["name"]), "invalid protocol name")
    rs = raw["resources"]
    require(type(rs) is dict and 0 < len(rs) <= 12 and all(name(k) for k in rs), "invalid resources")
    resources = tuple(sorted(rs))
    roles = names(raw["roles"], 16, "roles")
    initial=[]; caps=[]
    for k in resources:
        fields(rs[k], ["initial","capacity"], k)
        i,c = rs[k]["initial"],rs[k]["capacity"]
        require(integer(c,0,1000000) and integer(i,0,c), "invalid initial/capacity: "+k)
        initial.append(i);caps.append(c)
    def pred(p):
        fields(p,["weights","op","rhs"],"predicate")
        w=p["weights"]
        require(type(w) is dict and bool(w) and set(w)<=set(resources) and all(integer(v,-1000000,1000000) for v in w.values()), "invalid predicate weights")
        require(p["op"] in ("eq","le","ge") and integer(p["rhs"],-10**15,10**15),"invalid predicate")
        return Predicate(tuple(w.get(k,0) for k in resources),p["op"],p["rhs"])
    def preds(xs):
        require(type(xs) is list and len(xs)<=32,"invalid predicate list")
        return tuple(pred(p) for p in xs)
    invariants=preds(raw["invariants"])
    require(all(p.holds(initial) for p in invariants),"initial invariant violation")
    require(type(raw["actions"]) is list and 0<len(raw["actions"])<=64,"invalid actions")
    actions=[]; taken={"inspect"}
    for a in raw["actions"]:
        fields(a,["name","roles","guards","delta"],"action")
        n=a["name"]; require(name(n) and n not in taken,"invalid or duplicate operation")
        taken.add(n); ar=names(a["roles"],16,"action roles")
        require(set(ar)<=set(roles),"unknown role: "+n)
        d=a["delta"]
        require(type(d) is dict and bool(d) and set(d)<=set(resources) and all(integer(v,-1000000,1000000) for v in d.values()) and any(d.values()),"invalid delta: "+n)
        actions.append(Action(n,ar,preds(a["guards"]),tuple(d.get(k,0) for k in resources)))
    require(type(raw["goals"]) is list and len(raw["goals"])<=32,"invalid goals")
    byname={a.name:a for a in actions}; goals=[]
    for g in raw["goals"]:
        fields(g,["name","role","actions","predicates"],"goal")
        n=g["name"]; r=g["role"]
        require(name(n) and n not in taken and r in roles,"invalid or duplicate goal")
        taken.add(n); allowed=names(g["actions"],64,"goal actions")
        require(all(a in byname and r in byname[a].roles for a in allowed),"goal would escalate authority: "+n)
        ps=preds(g["predicates"]);require(bool(ps),"empty goal")
        goals.append(Goal(n,r,allowed,ps))
    return Protocol(raw["name"],resources,roles,tuple(initial),tuple(caps),invariants,tuple(actions),tuple(goals))

def next_state(p,s,a):
    if not all(g.holds(s) for g in a.guards):
        return None
    t=tuple(x+d for x,d in zip(s,a.delta))
    if not all(0<=x<=c for x,c in zip(t,p.caps)):
        return None
    require(all(g.holds(t) for g in p.invariants),
            "reachable invariant violation: "+a.name+" from "+str(s)+" to "+str(t))
    return t

def synthesize(raw):
    p=parse(raw)
    states=[p.initial]; idx={p.initial:0}; edges=[]; q=deque([p.initial])
    while q:
        s=q.popleft()
        for a in p.actions:
            t=next_state(p,s,a)
            if t is None:continue
            if t not in idx:
                require(len(states)<MAX_STATES,"state budget exceeded")
                idx[t]=len(states);states.append(t);q.append(t)
            edges.append((idx[s],a.name,idx[t]))
            require(len(edges)<=MAX_EDGES,"edge budget exceeded")
    byname={a.name:a for a in p.actions}
    # Reverse BFS per goal: exact shortest path in permitted action subgraph.
    plans={}; rows={r:{} for r in p.roles}
    for s,a,t in edges:
        for r in byname[a].roles:
            rows[r][(s,a)]=(t,(a,))
    plan_steps=0
    for g in p.goals:
        targets=[i for i,s in enumerate(states) if all(k.holds(s) for k in g.predicates)]
        rev=[[] for _ in states]
        for s,a,t in edges:
            if a in g.actions:rev[t].append((a,s))
        distance={i:0 for i in targets}; queue=deque(targets)
        while queue:
            t=queue.popleft()
            for a,s in sorted(rev[t]):
                if s not in distance:
                    distance[s]=distance[t]+1;queue.append(s)
        forward={}
        for s,a,t in edges:
            if a in g.actions and s in distance and t in distance and distance[s]==distance[t]+1:
                forward.setdefault(s,[]).append((a,t))
        for s in sorted(distance):
            if distance[s]==0:continue
            plan_steps += distance[s]
            require(plan_steps<=MAX_PLAN_STEPS, "plan budget exceeded")
            require(sum(map(len,rows.values()))<MAX_RULES, "generated rule budget exceeded")
            t=s; path=[]
            while distance[t]:
                a,u=min(forward[t]);path.append(a);t=u
            rows[g.role][(s,g.name)]=(t,tuple(path))
            plans[(g.name,s)]=tuple(path)
    require(sum(map(len,rows.values()))<=MAX_RULES,"generated rule budget exceeded")
    return p, states, edges, rows, plans

def manifest(raw):
    p,states,edges,rows,plans=synthesize(raw)
    return {
        "schema":1,"spec_sha256":digest(raw),"name":p.name,"resources":list(p.resources),"roles":list(p.roles),
        "states":[list(s) for s in states],"initial":0,"edges":[list(e) for e in edges],
        "rules":[{"role":r,"state":s,"operation":op,"target":t,"path":list(path)}
                 for r in p.roles for (s,op),(t,path) in sorted(rows[r].items())],
        "goals":[{"name":g.name,"role":g.role,"reachable_start_states":sum(1 for n,s in plans if n==g.name)} for g in p.goals],
        "max_version":MAX_VERSION
    }

def rholang(raw):
    p,states,edges,rows,plans=synthesize(raw)
    # A single private token serializes every state transition across all roles.
    # Bundles grant send-only access. The initializer itself is caller-scoped.
    caps=["role_"+r for r in p.roles]
    out=["contract factory(ready) = {","  new state, "+", ".join(caps)+" in {","    state!((0, 0)) |"]
    for role,cap in zip(p.roles,caps):
        out += [f"    contract {cap}(@op, @expected, ret) = {{",
                "      for (@(current, version) <- state) {",
                '        if (op == "inspect") {',
                "          state!((current, version)) | ret!((\"STATE\", current, version))",
                "        } else {",
                "          if (expected == version) {",
                f"            if (version < {MAX_VERSION}) {{",
                "              match (current, op) {"]
        for (s,op),(t,path) in sorted(rows[role].items()):
            out.append(f'                ({s}, "{op}") => {{ state!(({t}, version + 1)) | ret!(("OK", {t}, version + 1)) }}')
        out += ['                _ => { state!((current, version)) | ret!(("DENIED", current, version)) }',
                "              }","            } else {",
                '              state!((current, version)) | ret!(("EXHAUSTED", current, version))',
                "            }","          } else {",
                '            state!((current, version)) | ret!(("STALE", current, version))',
                "          }","        }","      }","    } |"]
    out += ["    ready!("+", ".join("bundle+{*"+c+"}" for c in caps)+")","  }","}"]
    return "\n".join(out)+"\n"

def simulate(m, state, version, role, op, expected):
    require(integer(state,0,len(m["states"])-1) and integer(version,0,m["max_version"]),"invalid machine state")
    require(role in m["roles"],"unknown role")
    if op=="inspect": return ("STATE",state,version)
    if type(expected) is not int or expected!=version:return ("STALE",state,version)
    if version==m["max_version"]:return ("EXHAUSTED",state,version)
    for row in m["rules"]:
        if (row["role"],row["state"],row["operation"])==(role,state,op):
            return ("OK",row["target"],version+1)
    return ("DENIED",state,version)
