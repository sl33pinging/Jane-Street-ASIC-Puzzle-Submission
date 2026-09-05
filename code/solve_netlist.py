#!/usr/bin/env python3
"""
Symbolically execute a recovered SKY130 gate-level netlist and solve for the
serial input sequence that drives a chosen output high.

    python3 solve_netlist.py puzzle_recovered.v \
        --top puzzle --serial I --enable enable --reset rst_n \
        --target success --bits 121 --settle 12

Unrolls the design cycle by cycle with Z3 booleans standing in for the input
bits, then asks the solver for an assignment making the target high.

Validate it first on a design whose answer you already know.
"""

import argparse
import re
import sys

from z3 import Bool, BoolVal, And, Or, Not, Xor, If, Solver, sat


# ---------------------------------------------------------------- cell library
# SKY130 hd combinational functions. Keys are the cell base name without the
# drive-strength suffix. Each entry maps output pin -> lambda over input pins.

def _f(expr_map):
    return expr_map


COMB = {
    "buf":      _f({"X": lambda p: p["A"]}),
    "clkbuf":   _f({"X": lambda p: p["A"]}),
    "dlygate4sd3": _f({"X": lambda p: p["A"]}),
    "inv":      _f({"Y": lambda p: Not(p["A"])}),
    "clkinv":   _f({"Y": lambda p: Not(p["A"])}),

    "and2":     _f({"X": lambda p: And(p["A"], p["B"])}),
    "and3":     _f({"X": lambda p: And(p["A"], p["B"], p["C"])}),
    "and4":     _f({"X": lambda p: And(p["A"], p["B"], p["C"], p["D"])}),
    "and2b":    _f({"X": lambda p: And(Not(p["A_N"]), p["B"])}),
    "and3b":    _f({"X": lambda p: And(Not(p["A_N"]), p["B"], p["C"])}),
    "and4b":    _f({"X": lambda p: And(Not(p["A_N"]), p["B"], p["C"], p["D"])}),
    "and4bb":   _f({"X": lambda p: And(Not(p["A_N"]), Not(p["B_N"]), p["C"], p["D"])}),

    "or2":      _f({"X": lambda p: Or(p["A"], p["B"])}),
    "or3":      _f({"X": lambda p: Or(p["A"], p["B"], p["C"])}),
    "or4":      _f({"X": lambda p: Or(p["A"], p["B"], p["C"], p["D"])}),
    "or2b":     _f({"X": lambda p: Or(p["A"], Not(p["B_N"]))}),
    "or3b":     _f({"X": lambda p: Or(p["A"], p["B"], Not(p["C_N"]))}),
    "or4b":     _f({"X": lambda p: Or(p["A"], p["B"], p["C"], Not(p["D_N"]))}),
    "or4bb":    _f({"X": lambda p: Or(p["A"], p["B"], Not(p["C_N"]), Not(p["D_N"]))}),

    "nand2":    _f({"Y": lambda p: Not(And(p["A"], p["B"]))}),
    "nand3":    _f({"Y": lambda p: Not(And(p["A"], p["B"], p["C"]))}),
    "nand4":    _f({"Y": lambda p: Not(And(p["A"], p["B"], p["C"], p["D"]))}),
    "nand2b":   _f({"Y": lambda p: Not(And(Not(p["A_N"]), p["B"]))}),
    "nand3b":   _f({"Y": lambda p: Not(And(Not(p["A_N"]), p["B"], p["C"]))}),
    "nand4b":   _f({"Y": lambda p: Not(And(Not(p["A_N"]), p["B"], p["C"], p["D"]))}),
    "nand4bb":  _f({"Y": lambda p: Not(And(Not(p["A_N"]), Not(p["B_N"]), p["C"], p["D"]))}),

    "nor2":     _f({"Y": lambda p: Not(Or(p["A"], p["B"]))}),
    "nor3":     _f({"Y": lambda p: Not(Or(p["A"], p["B"], p["C"]))}),
    "nor4":     _f({"Y": lambda p: Not(Or(p["A"], p["B"], p["C"], p["D"]))}),
    "nor2b":    _f({"Y": lambda p: Not(Or(p["A"], Not(p["B_N"])))}),
    "nor3b":    _f({"Y": lambda p: Not(Or(p["A"], p["B"], Not(p["C_N"])))}),
    "nor4b":    _f({"Y": lambda p: Not(Or(p["A"], p["B"], p["C"], Not(p["D_N"])))}),
    "nor4bb":   _f({"Y": lambda p: Not(Or(p["A"], p["B"], Not(p["C_N"]), Not(p["D_N"])))}),

    "xor2":     _f({"X": lambda p: Xor(p["A"], p["B"])}),
    "xor3":     _f({"X": lambda p: Xor(Xor(p["A"], p["B"]), p["C"])}),
    "xnor2":    _f({"Y": lambda p: Not(Xor(p["A"], p["B"]))}),
    "xnor3":    _f({"Y": lambda p: Not(Xor(Xor(p["A"], p["B"]), p["C"]))}),

    "mux2":     _f({"X": lambda p: If(p["S"], p["A1"], p["A0"])}),
    "mux2i":    _f({"Y": lambda p: Not(If(p["S"], p["A1"], p["A0"]))}),
    "mux4":     _f({"X": lambda p: If(p["S1"], If(p["S0"], p["A3"], p["A2"]),
                                      If(p["S0"], p["A1"], p["A0"]))}),

    # AOI / OAI family. aXY... = AND of X then Y ... feeding an OR (o = OR first).
    "a21o":     _f({"X": lambda p: Or(And(p["A1"], p["A2"]), p["B1"])}),
    "a21oi":    _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]), p["B1"]))}),
    "a21bo":    _f({"X": lambda p: Or(And(p["A1"], p["A2"]), Not(p["B1_N"]))}),
    "a21boi":   _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]), Not(p["B1_N"])))}),
    "a22o":     _f({"X": lambda p: Or(And(p["A1"], p["A2"]), And(p["B1"], p["B2"]))}),
    "a22oi":    _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]), And(p["B1"], p["B2"])))}),
    "a31o":     _f({"X": lambda p: Or(And(p["A1"], p["A2"], p["A3"]), p["B1"])}),
    "a31oi":    _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"], p["A3"]), p["B1"]))}),
    "a32o":     _f({"X": lambda p: Or(And(p["A1"], p["A2"], p["A3"]),
                                      And(p["B1"], p["B2"]))}),
    "a32oi":    _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"], p["A3"]),
                                          And(p["B1"], p["B2"])))}),
    "a41o":     _f({"X": lambda p: Or(And(p["A1"], p["A2"], p["A3"], p["A4"]), p["B1"])}),
    "a41oi":    _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"], p["A3"], p["A4"]),
                                          p["B1"]))}),
    "a211o":    _f({"X": lambda p: Or(And(p["A1"], p["A2"]), p["B1"], p["C1"])}),
    "a211oi":   _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]), p["B1"], p["C1"]))}),
    "a221o":    _f({"X": lambda p: Or(And(p["A1"], p["A2"]),
                                      And(p["B1"], p["B2"]), p["C1"])}),
    "a221oi":   _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]),
                                          And(p["B1"], p["B2"]), p["C1"]))}),
    "a222oi":   _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]),
                                          And(p["B1"], p["B2"]),
                                          And(p["C1"], p["C2"])))}),
    "a311o":    _f({"X": lambda p: Or(And(p["A1"], p["A2"], p["A3"]),
                                      p["B1"], p["C1"])}),
    "a311oi":   _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"], p["A3"]),
                                          p["B1"], p["C1"]))}),
    "a2111o":   _f({"X": lambda p: Or(And(p["A1"], p["A2"]),
                                      p["B1"], p["C1"], p["D1"])}),
    "a2111oi":  _f({"Y": lambda p: Not(Or(And(p["A1"], p["A2"]),
                                          p["B1"], p["C1"], p["D1"]))}),
    "a2bb2o":   _f({"X": lambda p: Or(And(Not(p["A1_N"]), Not(p["A2_N"])),
                                      And(p["B1"], p["B2"]))}),
    "a2bb2oi":  _f({"Y": lambda p: Not(Or(And(Not(p["A1_N"]), Not(p["A2_N"])),
                                          And(p["B1"], p["B2"])))}),

    "o21a":     _f({"X": lambda p: And(Or(p["A1"], p["A2"]), p["B1"])}),
    "o21ai":    _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"]), p["B1"]))}),
    "o21ba":    _f({"X": lambda p: And(Or(p["A1"], p["A2"]), Not(p["B1_N"]))}),
    "o21bai":   _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"]), Not(p["B1_N"])))}),
    "o22a":     _f({"X": lambda p: And(Or(p["A1"], p["A2"]), Or(p["B1"], p["B2"]))}),
    "o22ai":    _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"]), Or(p["B1"], p["B2"])))}),
    "o31a":     _f({"X": lambda p: And(Or(p["A1"], p["A2"], p["A3"]), p["B1"])}),
    "o31ai":    _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"], p["A3"]), p["B1"]))}),
    "o32a":     _f({"X": lambda p: And(Or(p["A1"], p["A2"], p["A3"]),
                                       Or(p["B1"], p["B2"]))}),
    "o32ai":    _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"], p["A3"]),
                                           Or(p["B1"], p["B2"])))}),
    "o41a":     _f({"X": lambda p: And(Or(p["A1"], p["A2"], p["A3"], p["A4"]), p["B1"])}),
    "o41ai":    _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"], p["A3"], p["A4"]),
                                           p["B1"]))}),
    "o211a":    _f({"X": lambda p: And(Or(p["A1"], p["A2"]), p["B1"], p["C1"])}),
    "o211ai":   _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"]), p["B1"], p["C1"]))}),
    "o221a":    _f({"X": lambda p: And(Or(p["A1"], p["A2"]),
                                       Or(p["B1"], p["B2"]), p["C1"])}),
    "o221ai":   _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"]),
                                           Or(p["B1"], p["B2"]), p["C1"]))}),
    "o311a":    _f({"X": lambda p: And(Or(p["A1"], p["A2"], p["A3"]),
                                       p["B1"], p["C1"])}),
    "o311ai":   _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"], p["A3"]),
                                           p["B1"], p["C1"]))}),
    "o2111a":   _f({"X": lambda p: And(Or(p["A1"], p["A2"]),
                                       p["B1"], p["C1"], p["D1"])}),
    "o2111ai":  _f({"Y": lambda p: Not(And(Or(p["A1"], p["A2"]),
                                           p["B1"], p["C1"], p["D1"]))}),
    "o2bb2a":   _f({"X": lambda p: And(Or(Not(p["A1_N"]), Not(p["A2_N"])),
                                       Or(p["B1"], p["B2"]))}),
    "o2bb2ai":  _f({"Y": lambda p: Not(And(Or(Not(p["A1_N"]), Not(p["A2_N"])),
                                           Or(p["B1"], p["B2"])))}),

    "conb":     _f({"HI": lambda p: BoolVal(True), "LO": lambda p: BoolVal(False)}),
}

# Sequential cells: (data pin, clock pin, reset pin or None, reset value,
#                    set pin or None, output pin)
SEQ = {
    "dfxtp": ("D", "CLK", None, None, None, "Q"),
    "dfrtp": ("D", "CLK", "RESET_B", False, None, "Q"),
    "dfstp": ("D", "CLK", None, None, "SET_B", "Q"),
    "dfbbn": ("D", "CLK_N", "RESET_B", False, "SET_B", "Q"),
}

# Cells with no logical function at all.
PHYSICAL = ("decap", "fill", "tap", "diode", "conb_", "fakediode")

SUPPLY = {"VPWR", "VGND", "VPB", "VNB"}


def base_cell(cell):
    """sky130_fd_sc_hd__nand2_2 -> nand2"""
    m = re.match(r"sky130_fd_sc_\w+?__([a-z0-9]+?)_\d+$", cell)
    return m.group(1) if m else None


def parse_netlist(path, top=None):
    """Return (ports, instances) for the top module. instances: (cell, name, {pin: net})."""
    txt = open(path, errors="replace").read()
    txt = re.sub(r"//[^\n]*", "", txt)

    mm = re.search(r"\bmodule\s+(\w+)\s*\(([^)]*)\)\s*;", txt)
    if not mm:
        sys.exit("no module declaration found")
    modname, portlist = mm.group(1), mm.group(2)
    if top and modname != top:
        print(f"# note: module in file is '{modname}', not '{top}'", file=sys.stderr)

    ports = [p.strip() for p in portlist.split(",") if p.strip()]

    insts = []
    pat = re.compile(r"(sky130_fd_sc_\w+)\s+(\S+)\s*\(([^;]*?)\)\s*;", re.S)
    conn = re.compile(r"\.(\w+)\s*\(\s*([^)]*?)\s*\)")
    for m in pat.finditer(txt):
        cell, name, body = m.group(1), m.group(2), m.group(3)
        pins = {}
        for c in conn.finditer(body):
            pin, net = c.group(1), c.group(2).strip()
            net = net.lstrip("\\").rstrip()
            pins[pin] = net
        insts.append((cell, name, pins))
    return modname, ports, insts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--top", default=None)
    ap.add_argument("--serial", required=True,
                    help="serial input port name(s), comma-separated")
    ap.add_argument("--enable", default=None)
    ap.add_argument("--reset", default=None, help="active-low reset port")
    ap.add_argument("--clock", default="clk")
    ap.add_argument("--target", required=True, help="output that must go high")
    ap.add_argument("--bits", type=int, required=True, help="input sequence length")
    ap.add_argument("--settle", type=int, default=12,
                    help="extra cycles after the input window")
    args = ap.parse_args()

    modname, ports, insts = parse_netlist(args.netlist, args.top)

    logic, seq, skipped = [], [], 0
    for cell, name, pins in insts:
        if any(s in cell for s in PHYSICAL) and "conb" not in cell:
            skipped += 1
            continue
        b = base_cell(cell)
        if b in SEQ:
            seq.append((b, name, pins))
        elif b in COMB:
            logic.append((b, name, pins))
        elif b and b.startswith("conb"):
            logic.append(("conb", name, pins))
        else:
            skipped += 1
            print(f"# unknown cell {cell} ({b}) -- skipped", file=sys.stderr)

    print(f"# top={modname} logic={len(logic)} seq={len(seq)} skipped={skipped}",
          file=sys.stderr)

    serials = [x.strip() for x in args.serial.split(",") if x.strip()]
    # input variables: one per serial port per cycle of the enable window
    invars = {sp: [Bool(f"{sp}_{i}") for i in range(args.bits)] for sp in serials}

    # flop state, initialised per its reset behaviour
    state = {}
    for b, name, pins in seq:
        out = pins[SEQ[b][5]]
        state[out] = BoolVal(False) if b in ("dfrtp", "dfxtp") else BoolVal(True)

    def eval_comb(cycle_inputs):
        """Resolve all combinational nets for one cycle. Returns net -> expr."""
        net = dict(cycle_inputs)
        for n, v in state.items():
            net.setdefault(n, v)
        net["VPWR"] = BoolVal(True)
        net["VGND"] = BoolVal(False)
        net["VPB"] = BoolVal(True)
        net["VNB"] = BoolVal(False)

        pending = list(logic)
        progress = True
        while pending and progress:
            progress = False
            still = []
            for b, name, pins in pending:
                fns = COMB[b]
                need = [p for p in pins
                        if p not in SUPPLY and p not in fns]
                if all(pins[p] in net for p in need):
                    vals = {p: net[pins[p]] for p in need}
                    for opin, fn in fns.items():
                        if opin in pins:
                            try:
                                net[pins[opin]] = fn(vals)
                            except KeyError:
                                still.append((b, name, pins))
                                break
                    else:
                        progress = True
                        continue
                else:
                    still.append((b, name, pins))
            pending = still
        if pending and not eval_comb.reported:
            eval_comb.reported = True
            print(f"# {len(pending)} gates unresolved:", file=sys.stderr)
            for b, name, pins in pending:
                fns = COMB[b]
                miss = [f"{p}={pins[p]}" for p in pins
                        if p not in SUPPLY and p not in fns
                        and pins[p] not in net]
                print(f"#   {b:10s} {name:40s} missing {miss}", file=sys.stderr)
        return net

    eval_comb.reported = False

    total = args.bits + args.settle
    target_expr = None
    for c in range(total):
        cyc_in = {}
        for sp in serials:
            cyc_in[sp] = invars[sp][c] if c < args.bits else BoolVal(False)
        if args.enable:
            cyc_in[args.enable] = BoolVal(c < args.bits)
        if args.reset:
            cyc_in[args.reset] = BoolVal(True)
        if args.clock:
            cyc_in[args.clock] = BoolVal(True)

        net = eval_comb(cyc_in)

        if args.target in net:
            target_expr = net[args.target]

        newstate = {}
        for b, name, pins in seq:
            d, _clk, rstp, _rv, setp, q = SEQ[b]
            dv = net.get(pins[d], BoolVal(False))
            if rstp and pins.get(rstp) in net:
                dv = And(net[pins[rstp]], dv)
            if setp and pins.get(setp) in net:
                dv = Or(Not(net[pins[setp]]), dv)
            newstate[pins[q]] = dv
        state.update(newstate)

        if (c + 1) % 20 == 0:
            print(f"# unrolled {c+1}/{total} cycles", file=sys.stderr)

    if target_expr is None:
        sys.exit(f"target '{args.target}' never resolved -- check the name")

    s = Solver()
    s.add(target_expr)
    print("# solving...", file=sys.stderr)
    if s.check() != sat:
        print("UNSAT -- no input of this length drives the target high")
        return

    m = s.model()
    for sp in serials:
        bits = "".join("1" if m.evaluate(v, model_completion=True) else "0"
                       for v in invars[sp])
        print(f"{sp}: {bits}")
        by = [bits[i:i + 8] for i in range(0, len(bits) - 7, 8)]
        asc = "".join(chr(int(x, 2)) if 32 <= int(x, 2) < 127 else "." for x in by)
        print(f"#   {len(bits)} bits, as bytes (msb-first): {asc}", file=sys.stderr)


if __name__ == "__main__":
    main()
