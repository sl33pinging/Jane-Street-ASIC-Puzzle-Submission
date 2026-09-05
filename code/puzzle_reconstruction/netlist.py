#!/usr/bin/env python3
"""Cell library, netlist parser and a reference gate-level simulator (pure Python).

The netlist path defaults to netlist/puzzle_recovered.v at the repo root and can
be overridden with the PUZZLE_NETLIST environment variable.
"""
import os, re, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = os.environ.get("PUZZLE_NETLIST",
                    os.path.join(_ROOT, "netlist", "puzzle_recovered.v"))
ANSWER = ("0000000101010000100000000000010101010000000000001010000001000001"
          "000000100000101000010000000100000010000010010001010000000")

def AND(*a): return all(a)
def OR(*a):  return any(a)
def NOT(a):  return not a
def XOR(a,b):return a != b
def MUX(s,a1,a0): return a1 if s else a0

COMB = {
 "buf":{"X":lambda p:p["A"]}, "clkbuf":{"X":lambda p:p["A"]},
 "inv":{"Y":lambda p:NOT(p["A"])}, "clkinv":{"Y":lambda p:NOT(p["A"])},
 "and2":{"X":lambda p:AND(p["A"],p["B"])},
 "and3":{"X":lambda p:AND(p["A"],p["B"],p["C"])},
 "and4":{"X":lambda p:AND(p["A"],p["B"],p["C"],p["D"])},
 "and2b":{"X":lambda p:AND(NOT(p["A_N"]),p["B"])},
 "and3b":{"X":lambda p:AND(NOT(p["A_N"]),p["B"],p["C"])},
 "and4b":{"X":lambda p:AND(NOT(p["A_N"]),p["B"],p["C"],p["D"])},
 "and4bb":{"X":lambda p:AND(NOT(p["A_N"]),NOT(p["B_N"]),p["C"],p["D"])},
 "or2":{"X":lambda p:OR(p["A"],p["B"])},
 "or3":{"X":lambda p:OR(p["A"],p["B"],p["C"])},
 "or4":{"X":lambda p:OR(p["A"],p["B"],p["C"],p["D"])},
 "or2b":{"X":lambda p:OR(p["A"],NOT(p["B_N"]))},
 "or3b":{"X":lambda p:OR(p["A"],p["B"],NOT(p["C_N"]))},
 "or4b":{"X":lambda p:OR(p["A"],p["B"],p["C"],NOT(p["D_N"]))},
 "or4bb":{"X":lambda p:OR(p["A"],p["B"],NOT(p["C_N"]),NOT(p["D_N"]))},
 "nand2":{"Y":lambda p:NOT(AND(p["A"],p["B"]))},
 "nand3":{"Y":lambda p:NOT(AND(p["A"],p["B"],p["C"]))},
 "nand4":{"Y":lambda p:NOT(AND(p["A"],p["B"],p["C"],p["D"]))},
 "nand2b":{"Y":lambda p:NOT(AND(NOT(p["A_N"]),p["B"]))},
 "nand3b":{"Y":lambda p:NOT(AND(NOT(p["A_N"]),p["B"],p["C"]))},
 "nand4b":{"Y":lambda p:NOT(AND(NOT(p["A_N"]),p["B"],p["C"],p["D"]))},
 "nand4bb":{"Y":lambda p:NOT(AND(NOT(p["A_N"]),NOT(p["B_N"]),p["C"],p["D"]))},
 "nor2":{"Y":lambda p:NOT(OR(p["A"],p["B"]))},
 "nor3":{"Y":lambda p:NOT(OR(p["A"],p["B"],p["C"]))},
 "nor4":{"Y":lambda p:NOT(OR(p["A"],p["B"],p["C"],p["D"]))},
 "nor2b":{"Y":lambda p:NOT(OR(p["A"],NOT(p["B_N"])))},
 "nor3b":{"Y":lambda p:NOT(OR(p["A"],p["B"],NOT(p["C_N"])))},
 "nor4b":{"Y":lambda p:NOT(OR(p["A"],p["B"],p["C"],NOT(p["D_N"])))},
 "nor4bb":{"Y":lambda p:NOT(OR(p["A"],p["B"],NOT(p["C_N"]),NOT(p["D_N"])))},
 "xor2":{"X":lambda p:XOR(p["A"],p["B"])},
 "xnor2":{"Y":lambda p:NOT(XOR(p["A"],p["B"]))},
 "mux2":{"X":lambda p:MUX(p["S"],p["A1"],p["A0"])},
 "mux2i":{"Y":lambda p:NOT(MUX(p["S"],p["A1"],p["A0"]))},
 "a21o":{"X":lambda p:OR(AND(p["A1"],p["A2"]),p["B1"])},
 "a21oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"]),p["B1"]))},
 "a21bo":{"X":lambda p:OR(AND(p["A1"],p["A2"]),NOT(p["B1_N"]))},
 "a21boi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"]),NOT(p["B1_N"])))},
 "a22o":{"X":lambda p:OR(AND(p["A1"],p["A2"]),AND(p["B1"],p["B2"]))},
 "a22oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"]),AND(p["B1"],p["B2"])))},
 "a31o":{"X":lambda p:OR(AND(p["A1"],p["A2"],p["A3"]),p["B1"])},
 "a31oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"],p["A3"]),p["B1"]))},
 "a32o":{"X":lambda p:OR(AND(p["A1"],p["A2"],p["A3"]),AND(p["B1"],p["B2"]))},
 "a32oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"],p["A3"]),AND(p["B1"],p["B2"])))},
 "a41o":{"X":lambda p:OR(AND(p["A1"],p["A2"],p["A3"],p["A4"]),p["B1"])},
 "a41oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"],p["A3"],p["A4"]),p["B1"]))},
 "a211o":{"X":lambda p:OR(AND(p["A1"],p["A2"]),p["B1"],p["C1"])},
 "a211oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"]),p["B1"],p["C1"]))},
 "a221o":{"X":lambda p:OR(AND(p["A1"],p["A2"]),AND(p["B1"],p["B2"]),p["C1"])},
 "a221oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"]),AND(p["B1"],p["B2"]),p["C1"]))},
 "a311o":{"X":lambda p:OR(AND(p["A1"],p["A2"],p["A3"]),p["B1"],p["C1"])},
 "a311oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"],p["A3"]),p["B1"],p["C1"]))},
 "a2111o":{"X":lambda p:OR(AND(p["A1"],p["A2"]),p["B1"],p["C1"],p["D1"])},
 "a2111oi":{"Y":lambda p:NOT(OR(AND(p["A1"],p["A2"]),p["B1"],p["C1"],p["D1"]))},
 "a2bb2o":{"X":lambda p:OR(AND(NOT(p["A1_N"]),NOT(p["A2_N"])),AND(p["B1"],p["B2"]))},
 "a2bb2oi":{"Y":lambda p:NOT(OR(AND(NOT(p["A1_N"]),NOT(p["A2_N"])),AND(p["B1"],p["B2"])))},
 "o21a":{"X":lambda p:AND(OR(p["A1"],p["A2"]),p["B1"])},
 "o21ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"]),p["B1"]))},
 "o21ba":{"X":lambda p:AND(OR(p["A1"],p["A2"]),NOT(p["B1_N"]))},
 "o21bai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"]),NOT(p["B1_N"])))},
 "o22a":{"X":lambda p:AND(OR(p["A1"],p["A2"]),OR(p["B1"],p["B2"]))},
 "o22ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"]),OR(p["B1"],p["B2"])))},
 "o31a":{"X":lambda p:AND(OR(p["A1"],p["A2"],p["A3"]),p["B1"])},
 "o31ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"],p["A3"]),p["B1"]))},
 "o32a":{"X":lambda p:AND(OR(p["A1"],p["A2"],p["A3"]),OR(p["B1"],p["B2"]))},
 "o32ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"],p["A3"]),OR(p["B1"],p["B2"])))},
 "o211a":{"X":lambda p:AND(OR(p["A1"],p["A2"]),p["B1"],p["C1"])},
 "o211ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"]),p["B1"],p["C1"]))},
 "o221a":{"X":lambda p:AND(OR(p["A1"],p["A2"]),OR(p["B1"],p["B2"]),p["C1"])},
 "o221ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"]),OR(p["B1"],p["B2"]),p["C1"]))},
 "o311a":{"X":lambda p:AND(OR(p["A1"],p["A2"],p["A3"]),p["B1"],p["C1"])},
 "o311ai":{"Y":lambda p:NOT(AND(OR(p["A1"],p["A2"],p["A3"]),p["B1"],p["C1"]))},
 "o2bb2a":{"X":lambda p:AND(OR(NOT(p["A1_N"]),NOT(p["A2_N"])),OR(p["B1"],p["B2"]))},
 "o2bb2ai":{"Y":lambda p:NOT(AND(OR(NOT(p["A1_N"]),NOT(p["A2_N"])),OR(p["B1"],p["B2"])))},
 "conb":{"HI":lambda p:True,"LO":lambda p:False},
}
SEQ={"dfxtp":("D","CLK",None,None,"Q"),
     "dfrtp":("D","CLK","RESET_B",None,"Q"),
     "dfstp":("D","CLK",None,"SET_B","Q")}
PHYSICAL=("decap","fill","tap","diode","fakediode")
SUPPLY={"VPWR","VGND","VPB","VNB"}

def base_cell(c):
    m=re.match(r"sky130_fd_sc_\w+?__([a-z0-9]+?)_\d+$",c); return m.group(1) if m else None

def parse(path):
    txt=re.sub(r"//[^\n]*","",open(path,errors="replace").read())
    insts=[]
    pat=re.compile(r"(sky130_fd_sc_\w+)\s+(\S+)\s*\(([^;]*?)\)\s*;",re.S)
    conn=re.compile(r"\.(\w+)\s*\(\s*([^)]*?)\s*\)")
    for m in pat.finditer(txt):
        cell,name,body=m.group(1),m.group(2),m.group(3)
        pins={c.group(1):c.group(2).strip().lstrip("\\").rstrip() for c in conn.finditer(body)}
        insts.append((cell,name,pins))
    return insts

class Sim:
    def __init__(self,path=NL):
        insts=parse(path); self.logic=[]; self.seq=[]
        for cell,name,pins in insts:
            if any(s in cell for s in PHYSICAL): continue
            b=base_cell(cell)
            if b in SEQ: self.seq.append((b,name,pins))
            elif b in COMB: self.logic.append((b,name,pins))
            elif b and b.startswith("conb"): self.logic.append(("conb",name,pins))
            else: print("# unknown",cell,file=sys.stderr)
        self.reset()
    def reset(self):
        self.state={}
        for b,name,pins in self.seq:
            self.state[pins[SEQ[b][4]]] = (b=="dfstp")
    def eval(self,ins,force=None):
        net=dict(ins)
        for n,v in self.state.items(): net.setdefault(n,v)
        net.update({"VPWR":True,"VGND":False,"VPB":True,"VNB":False})
        if force: net.update(force)
        pending=list(self.logic); prog=True
        while pending and prog:
            prog=False; still=[]
            for b,name,pins in pending:
                fns=COMB[b]
                need=[p for p in pins if p not in SUPPLY and p not in fns]
                if all(pins[p] in net for p in need):
                    vals={p:net[pins[p]] for p in need}
                    for opin,fn in fns.items():
                        if opin in pins:
                            tgt=pins[opin]
                            if force and tgt in force: continue
                            net[tgt]=fn(vals)
                    prog=True
                else: still.append((b,name,pins))
            pending=still
        self.unresolved=pending
        return net
    def tick(self,ins,force=None):
        net=self.eval(ins,force)
        new={}
        for b,name,pins in self.seq:
            d,_c,rstp,setp,q=SEQ[b]
            dv=net.get(pins[d],False)
            if rstp and pins.get(rstp) in net: dv = net[pins[rstp]] and dv
            if setp and pins.get(setp) in net: dv = (not net[pins[setp]]) or dv
            new[pins[q]]=dv
        self.state.update(new); return net

OBITS=[f"O[{i}]" for i in range(8)]

def run(bits, post=48, force=None, sim=None, nbits=None):
    """bits: string of '0'/'1' fed MSB-first (bits[0] first). Returns (msg, success_flags)."""
    s = sim or Sim()
    s.reset()
    nbits = nbits if nbits is not None else len(bits)
    base={"clk":True,"rst_n":False,"enable":False,"I":False}
    for _ in range(2): s.tick(dict(base),force)
    base["rst_n"]=True
    s.tick(dict(base),force)
    for k in range(nbits):
        s.tick({**base,"enable":True,"I":bits[k]=='1'},force)
    chars=[]; succ=[]
    for k in range(post):
        net=s.tick(dict(base),force)
        v=0
        for i,ob in enumerate(OBITS):
            if net.get(ob,False): v|=1<<i
        chars.append(v); succ.append(net.get("success",False))
    return chars,succ

def render(chars):
    return "".join(chr(c) if 32<=c<127 else ("." if c==0 else f"<{c:02x}>") for c in chars)

if __name__=="__main__":
    sim=Sim()
    print(f"parsed {len(sim.logic)} combinational cells, {len(sim.seq)} flops")
    for label,b in [("CORRECT",ANSWER),("ZEROS","0"*121),("ONES","1"*121)]:
        c,s_=run(b,sim=sim)
        print(f"  {label:8s} success={any(s_)}  O={render(c)!r}")
