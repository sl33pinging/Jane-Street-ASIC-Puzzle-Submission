#!/usr/bin/env python3
"""Fast topologically-ordered gate-level simulator (~0.25 s per 165-cycle run)."""
from netlist import Sim, COMB, SEQ, SUPPLY, OBITS, ANSWER

class Fast:
    def __init__(self):
        s = Sim()
        self.seq = s.seq
        # determine a topological order by simulating resolution with a 'known' set
        known = set(SUPPLY) | {"clk","rst_n","enable","I"}
        for b,n,p in s.seq: known.add(p[SEQ[b][4]])
        pending = list(s.logic); order=[]
        while pending:
            still=[]; prog=False
            for b,name,pins in pending:
                fns = COMB[b]
                need=[p for p in pins if p not in SUPPLY and p not in fns]
                if all(pins[p] in known for p in need):
                    order.append((b,name,pins))
                    for opin in fns:
                        if opin in pins: known.add(pins[opin])
                    prog=True
                else: still.append((b,name,pins))
            if not prog:
                print("WARNING: %d gates in comb loop" % len(still)); break
            pending=still
        self.order=order
        self.flopq=[p[SEQ[b][4]] for b,n,p in s.seq]
        self.reset()

    def reset(self):
        self.st={}
        for b,n,p in self.seq: self.st[p[SEQ[b][4]]] = (b=="dfstp")

    def tick(self, I, enable, rst_n=True, force=None):
        net = dict(self.st)
        net.update({"VPWR":True,"VGND":False,"VPB":True,"VNB":False,
                    "clk":True,"rst_n":rst_n,"enable":enable,"I":I})
        if force: net.update(force)
        for b,name,pins in self.order:
            fns=COMB[b]
            vals={p:net[pins[p]] for p in pins if p not in SUPPLY and p not in fns}
            for opin,fn in fns.items():
                if opin in pins:
                    t=pins[opin]
                    if force and t in force: continue
                    net[t]=fn(vals)
        new={}
        for b,name,pins in self.seq:
            d,_c,rstp,setp,q = SEQ[b]
            dv=net.get(pins[d],False)
            if rstp and pins.get(rstp) in net: dv = net[pins[rstp]] and dv
            if setp and pins.get(setp) in net: dv = (not net[pins[setp]]) or dv
            new[pins[q]]=dv
        self.st=new
        if force:
            for k,v in force.items():
                if k in self.st: self.st[k]=v
        return net

    def run(self, bits, post=44, force=None, nbits=121):
        self.reset()
        if force:
            for k,v in force.items():
                if k in self.st: self.st[k]=v
        for _ in range(2): self.tick(False,False,False,force)
        self.tick(False,False,True,force)
        for k in range(nbits): self.tick(bits[k]=='1',True,True,force)
        out=[]; succ=False
        for k in range(post):
            net=self.tick(False,False,True,force)
            v=0
            for i,ob in enumerate(OBITS):
                if net.get(ob,False): v|=1<<i
            out.append(v); succ = succ or net.get("success",False)
        return out,succ

def msg(out):
    s="".join(chr(c) if 32<=c<127 else ("\x00" if c==0 else "�") for c in out)
    return s.strip("\x00")

if __name__=="__main__":
    import time
    f=Fast(); t=time.time(); o,s=f.run(ANSWER)
    print(f"{time.time()-t:.3f}s  success={s}  O={msg(o)!r}")
