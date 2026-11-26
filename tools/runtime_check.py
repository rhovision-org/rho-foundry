"""Run generated contracts on a pinned Rholo binary, in an isolated ephemeral devnet."""
import argparse
from collections import Counter, deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
from foundry.core import manifest, rholang, simulate, load_spec

ROOT=Path(__file__).resolve().parents[1]
COMMIT="e63b7e5a8ccfcc25ff64860ac989d95a748eaaca"
BINARY_SHA="232d12bd5d3fadc8371c26ec6a888ea48a4062b1187bb63c35b9d19423f28ead"

def sha(path):
    with open(path,"rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kw):raise ValueError("redirect refused")

def ports():
    ss=[]
    try:
        for _ in range(6):
            s=socket.socket();s.bind(("127.0.0.1",0));ss.append(s)
        return [s.getsockname()[1] for s in ss]
    finally:
        for s in ss:s.close()

def term(raw, body):
    rs=", ".join("cap"+str(i) for i in range(len(raw["roles"])))
    return "new out, factory, ready in { "+rholang(raw)+" | factory!(*ready) | for ("+rs+" <- ready) { "+body+" } }"

def seq_body(raw, calls):
    inner="Nil"
    for i,(role,op,ver) in reversed(list(enumerate(calls))):
        cap="cap"+str(raw["roles"].index(role)); ack="ack"+str(i)
        inner=f'new {ack} in {{ {cap}!({json.dumps(op)}, {ver}, *{ack}) | for (@(status, sid, version) <- {ack}) {{ out!(({i}, status, sid, version)) | {inner} }} }}'
    return inner

def seq(raw,calls):
    m=manifest(raw);s=0;v=0;expected=[]
    for i,(r,a,e) in enumerate(calls):
        status,s,v=simulate(m,s,v,r,a,e);expected.append([i,status,s,v])
    return term(raw,seq_body(raw,calls)),expected

def decode(item):
    if not isinstance(item,dict) or len(item)!=1:raise ValueError("malformed expression")
    k,v=next(iter(item.items()))
    if isinstance(v,dict):v=v.get("data")
    if k=="ExprTuple" and isinstance(v,list):return [decode(x) for x in v]
    if k=="ExprInt" and type(v) is int:return v
    if k=="ExprString" and type(v) is str:return v
    raise ValueError("unexpected expression: "+str(item)[:150])

def prefixes(m):
    paths={0:[]};q=deque([0])
    while q:
        s=q.popleft()
        for row in m["rules"]:
            if row["state"]==s and len(row["path"])==1 and row["operation"]==row["path"][0] and row["target"] not in paths:
                paths[row["target"]]=paths[s]+[(row["role"],row["operation"],len(paths[s]))]
                q.append(row["target"])
    if len(paths)!=len(m["states"]):raise ValueError("unreachable manifest state")
    return paths

def check(request,anchor,quick):
    rows=[]
    def invoke(name,source,expected):
        reply=request("/api/explore-deploy",source)
        if reply.get("block",{}).get("blockHash")!=anchor or reply.get("replySource")!="firstPrivateName":
            raise ValueError("unexpected response anchor or capture: "+str(reply)[:250])
        actual=sorted((decode(x) for x in reply["expr"]),key=lambda x:x[0])
        if actual!=expected:raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        rows.append({"name":name,"expected":expected,"actual":actual,"passed":True})
        if len(rows)%20==0:print("runtime probes:",len(rows),flush=True)
    esc=load_spec((ROOT/"examples/escrow.json").read_text())
    res=load_spec((ROOT/"examples/reservation.json").read_text())
    for raw,goal,role in [(esc,"settle","settler"),(res,"sellout","agent")]:
        source,expected=seq(raw,[(role,goal,0),(role,"inspect",0),(role,goal,0)])
        invoke(raw["name"]+"-macro",source,expected)
        m=manifest(raw);paths=prefixes(m)
        if not quick:
            operations=[a["name"] for a in raw["actions"]]+[g["name"] for g in raw["goals"]]+["unknown","inspect"]
            for s in range(len(m["states"])):
                prefix=paths[s]
                for r in raw["roles"]:
                    for op in operations:
                        source,expected=seq(raw,prefix+[(r,op,len(prefix)),(r,"inspect",0)])
                        invoke(f'{raw["name"]}:{s}:{r}:{op}',source,expected)
    source,expected=seq(esc,[("buyer","fund",0),("seller","settle",1),("settler","settle",1),("buyer","fund",0)])
    invoke("partial-recovery-and-role-denial",source,expected)
    # Competing requests share one starting version; one must win, one must be stale.
    race=term(esc,'new a,b,c in { cap2!("settle",0,*a) | cap2!("settle",0,*b) | for (@(x,s,v) <- a; @(y,t,w) <- b) { cap0!("inspect",0,*c) | for (@(z,u,k) <- c) { match (x,y) { ("OK","STALE") => { out!((0,x,s,v)) | out!((1,y,t,w)) } ("STALE","OK") => { out!((0,y,t,w)) | out!((1,x,s,v)) } _ => { out!((0,"BAD",0,0)) } } | out!((2,z,u,k)) } } }')
    target=simulate(manifest(esc),0,0,"settler","settle",0)[1]
    for i in range(3):invoke("race-"+str(i),race,[[0,"OK",target,1],[1,"STALE",target,1],[2,"STATE",target,1]])
    # Two factory invocations have independent private state, even within one term.
    isolation='new out, factory, ra, rb in { '+rholang(esc)+' | factory!(*ra) | factory!(*rb) | for (a0,a1,a2 <- ra; b0,b1,b2 <- rb) { new x,y in { a2!("settle",0,*x) | b2!("inspect",0,*y) | for (@(s,i,v) <- x; @(t,j,w) <- y) { out!((0,s,i,v)) | out!((1,t,j,w)) } } } }'
    invoke("instance-isolation",isolation,[[0,"OK",target,1],[1,"STATE",0,0]])
    return rows

def run(binary,emulator=None,libdir=None,quick=False):
    if sha(binary)!=BINARY_SHA:raise ValueError("binary digest mismatch")
    cmd=([str(emulator)] if emulator else [])+[str(binary)]
    openssl=shutil.which("openssl")
    if not openssl:raise ValueError("OpenSSL required for synthetic validator key")
    with tempfile.TemporaryDirectory(prefix="foundry-rholo-") as td:
        d=Path(td); home=d/"home";home.mkdir()
        env={"PATH":os.path.dirname(openssl)+":"+os.defpath,"HOME":str(home)}
        if libdir:env["LD_LIBRARY_PATH"]=str(libdir)+":"+str(Path(openssl).parent.parent/"lib")
        version=subprocess.check_output(cmd+["--version"],env=env,stderr=subprocess.DEVNULL,timeout=20,text=True).strip()
        if version!="rnode 0.1.0 ("+COMMIT+")":raise ValueError("revision mismatch: "+version)
        pem=subprocess.check_output([openssl,"ecparam","-name","secp256k1","-genkey","-noout"],env=env,stderr=subprocess.DEVNULL,timeout=10)
        keytext=subprocess.check_output([openssl,"ec","-text","-noout"],input=pem,env=env,stderr=subprocess.DEVNULL,timeout=10).decode()
        priv,pub=keytext.split("priv:",1)[1].split("pub:",1)
        priv=re.sub("[^a-fA-F0-9]","",priv);pub=re.sub("[^a-fA-F0-9]","",pub.split("ASN1 OID:",1)[0])
        if len(priv)!=64 or len(pub)!=130:raise ValueError("bad synthetic key")
        key=d/"key";key.write_text(priv+"\n");key.chmod(0o600)
        bonds=d/"bonds";bonds.write_text(pub+" 100\n");wallets=d/"wallets";wallets.touch()
        port,disc,external,internal,http,admin=ports();network="foundry-"+uuid.uuid4().hex
        args=cmd+["run","--standalone","--no-upnp","--dev-mode","--host","127.0.0.1","--api-host","127.0.0.1","--network-id",network,"--shard-name","foundry-isolated","--data-dir",str(d/"data"),"--protocol-port",str(port),"--discovery-port",str(disc),"--api-port-grpc-external",str(external),"--api-port-grpc-internal",str(internal),"--api-port-http",str(http),"--api-port-admin-http",str(admin),"--thread-pool-size","2","--autogen-shard-size","1","--validator-private-key-path",str(key),"--validator-public-key",pub,"--bonds-file",str(bonds),"--wallets-file",str(wallets),"--allow-under-minimum","--accept-under-minimum-risk","--no-attest-on-new-blocks"]
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        def request(path,body=None):
            req=urllib.request.Request(f"http://127.0.0.1:{http}"+path,data=None if body is None else json.dumps(body).encode(),headers={"Content-Type":"application/json"})
            try:
                with opener.open(req,timeout=30) as r:data=r.read(2_000_001)
            except urllib.error.HTTPError as e:raise ValueError(f"HTTP {e.code}: "+e.read(1000).decode(errors="replace")) from e
            if len(data)>2_000_000:raise ValueError("body too large")
            return json.loads(data)
        log=d/"node.log"
        with log.open("wb") as stream:
            proc=subprocess.Popen(args,env=env,cwd=d,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream)
            try:
                deadline=time.monotonic()+90;status=None
                while time.monotonic()<deadline and proc.poll() is None:
                    try:
                        candidate=request("/api/status")
                        if isinstance(candidate,dict) and isinstance(candidate.get("checkpoint"),dict) and candidate["checkpoint"].get("anchor") and candidate.get("syncPhase")=="running":status=candidate;break
                    except (ValueError,OSError):pass
                    time.sleep(.5)
                if status is None:raise ValueError("isolated node startup failed: "+log.read_text(errors="replace").split("___ Begin jemalloc statistics ___")[0][-4000:])
                if status.get("networkId")!=network or status.get("shardId")!="/foundry-isolated" or status.get("peers")!=0 or status.get("devMode") is not True:raise ValueError("isolation mismatch")
                anchor=status["checkpoint"]["anchor"]; print("isolated runtime ready",flush=True)
                rows=check(request,anchor,quick)
                end=request("/api/status")
                if end.get("networkId")!=network or end.get("peers")!=0 or end.get("latestBlockNumber")!=status.get("latestBlockNumber") or end["checkpoint"]["anchor"]!=anchor:raise ValueError("chain changed")
                return {"runtime":version,"binary_sha256":BINARY_SHA,"compiler_sha256":sha(ROOT/"foundry/core.py"),"harness_sha256":sha(Path(__file__)),"emulated":bool(emulator),"quick":quick,"peers":0,"height_before":status["latestBlockNumber"],"height_after":end["latestBlockNumber"],"runs":len(rows),"passed":True,"rows":rows}
            finally:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()

def main():
    p=argparse.ArgumentParser();p.add_argument("binary",type=Path);p.add_argument("--emulator",type=Path);p.add_argument("--libdir",type=Path);p.add_argument("--quick",action="store_true");p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    result=run(a.binary.resolve(),a.emulator.resolve() if a.emulator else None,a.libdir.resolve() if a.libdir else None,a.quick)
    a.out.write_text(json.dumps(result,indent=2)+"\n");print("PASS",result["runs"],flush=True)
if __name__=="__main__":main()
