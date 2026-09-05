#!/usr/bin/env python3
"""Recover the 11x11 Star Battle grid from the silicon.

Uses no prior knowledge of the solution.

Method -- "drive exactly one star and see what sticks":

  1. For each position p in 0..120, run the full 121-cycle input window with a
     grid that is all zeros except a single 1 at p. Snapshot all 92 flops at
     the moment enable drops and diff against the all-zeros run. That gives
     F(p), the flops that position p alone disturbed.
  2. Invert the map: flop -> set of positions that touch it.
  3. Find every exact partition of {0..120} built from those position sets.

Why it works: a constraint that counts occurrences within a group whose cells
are scattered through the input stream needs one persistent counter per group.
A single star increments exactly one counter in each such family, flipping its
low bit -- so a counter's low-bit flop is touched by precisely its group.

Rows never appear, and that absence is informative: a row is 11 CONSECUTIVE
cells in time, so one reusable counter that clears at each row boundary
suffices, and it carries no per-row signature at the end of the stream. Same
for adjacency, which is a sliding window. The probe reveals exactly those
constraints that need parallel persistent state.

    python analysis/probe_regions.py          # writes data/regions.json
"""
import collections
import json
import os

from fastsim import Fast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = 11
LABELS = "ABCDEFGHIJK"


def signatures(f):
    """p -> frozenset of flops whose end-of-window value differs from all-zeros."""
    def state(bits):
        f.reset()
        for _ in range(2):
            f.tick(False, False, False)
        f.tick(False, False, True)
        for k in range(121):
            f.tick(bits[k] == "1", True, True)
        return dict(f.st)

    zero = state("0" * 121)
    out = {}
    for p in range(121):
        b = ["0"] * 121
        b[p] = "1"
        st = state("".join(b))
        out[p] = frozenset(k for k, v in st.items() if v != zero[k])
    return out


def exact_covers(sets, universe, limit=20):
    """Every exact partition of `universe` drawn from the values of `sets`."""
    cands = [(k, v) for k, v in sets.items() if v]
    found = []

    def search(remaining, chosen):
        if not remaining:
            found.append(list(chosen))
            return
        if len(found) >= limit:
            return
        pivot = min(remaining)
        for k, v in cands:
            if pivot in v and v <= remaining:
                chosen.append(k)
                search(remaining - v, chosen)
                chosen.pop()

    search(frozenset(universe), [])
    return found


def connected(cells):
    """True if the cells form one edge-connected blob on the 11x11 grid."""
    cells = set(cells)
    seen = {next(iter(cells))}
    stack = list(seen)
    while stack:
        p = stack.pop()
        r, c = divmod(p, N)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (r + dr) * N + (c + dc)
            if 0 <= r + dr < N and 0 <= c + dc < N and q in cells and q not in seen:
                seen.add(q)
                stack.append(q)
    return len(seen) == len(cells)


def main():
    f = Fast()
    print("probing 121 single-star grids ...")
    F = signatures(f)

    sets = collections.defaultdict(set)
    for p, flops in F.items():
        for k in flops:
            sets[k].add(p)
    sets = {k: frozenset(v) for k, v in sets.items()}
    print("flops touched by at least one probe: %d of 92\n" % len(sets))

    covers = exact_covers(sets, range(121))
    print("exact partitions of the 121 cells: %d" % len(covers))
    cols = regs = None
    for i, sol in enumerate(covers):
        groups = [sorted(sets[k]) for k in sol]
        sizes = sorted(len(g) for g in groups)
        mod11 = all(len({p % N for p in g}) == 1 for g in groups)
        if len(groups) == 1:
            kind = "trivial (one global counter bit)"
        elif mod11:
            kind = "COLUMNS"
            cols = groups
        else:
            kind = "REGIONS"
            regs = groups
        print("  cover %d: %2d groups, sizes=%s  -> %s" % (i, len(groups), sizes, kind))

    assert cols and regs, "expected one regular and one irregular partition"
    print("\nevery region edge-connected: %s" % all(connected(g) for g in regs))

    regs.sort(key=min)
    label = {p: LABELS[i] for i, g in enumerate(regs) for p in g}
    print("\nregion map:")
    for r in range(N):
        print("   " + " ".join(label[r * N + c] for c in range(N)))

    out = os.path.join(ROOT, "data", "regions.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(
            {
                "grid": N,
                "columns": cols,
                "regions": regs,
                "map": "".join(label[p] for p in range(121)),
            },
            fh,
            indent=1,
        )
    print("\nwrote %s" % out)


if __name__ == "__main__":
    main()