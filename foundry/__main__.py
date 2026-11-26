import argparse
import json
from pathlib import Path
import sys
import tempfile
import shutil
from .core import load_spec,compile_protocol,SpecError
from .symbolic import compile_symbolic
from . import __version__

def main():
    p=argparse.ArgumentParser(description="Synthesize atomic resource protocols into Rholang")
    p.add_argument("--version",action="version",version=__version__)
    p.add_argument("spec",type=Path)
    p.add_argument("--out",type=Path,required=True,help="new output directory")
    p.add_argument("--symbolic",action="store_true",help="compile inductively checked counter rules")
    a=p.parse_args()
    temp=None
    try:
        with a.spec.open("rb") as f:
            b=f.read(262145)
        if len(b)>262144:raise SpecError("spec byte limit")
        raw=load_spec(b.decode("utf-8"))
        m,code=(compile_symbolic if a.symbolic else compile_protocol)(raw)
        if a.out.exists():raise SpecError("output directory already exists")
        temp=Path(tempfile.mkdtemp(prefix=".foundry-",dir=a.out.parent))
        (temp/"contract.rho").write_text(code,encoding="utf-8")
        (temp/"machine.json").write_text(json.dumps(m,indent=2)+"\n",encoding="utf-8")
        temp.rename(a.out);temp=None
        result = {"status": "COMPILED", "output": str(a.out)}
        if a.symbolic:
            result.update(backend="symbolic", primitives=len(m["preservation"]), macros=len(m["macros"]))
        else:
            result.update(states=len(m["states"]), transitions=len(m["edges"]), rules=len(m["rules"]))
        print(json.dumps(result))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as e:
        print(json.dumps({"status":"ERROR","reason":str(e)}),file=sys.stderr);return 2
    finally:
        if temp is not None:shutil.rmtree(temp)
if __name__=="__main__":raise SystemExit(main())
