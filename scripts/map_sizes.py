#!/usr/bin/env python3
import re, sys
from collections import defaultdict

if len(sys.argv) != 2:
    raise SystemExit("usage: map_sizes.py <link.map>")

totals = defaultdict(int)
symbols = []
rx = re.compile(r"^\s*\.\S+\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)\s+(.+?\.a\([^)]*\)|\S+\.o)\s*$")
for line in open(sys.argv[1], errors="replace"):
    m = rx.match(line.rstrip())
    if not m:
        continue
    size = int(m.group(1), 16)
    obj = m.group(2)
    if size <= 0:
        continue
    if ".a(" in obj:
        archive = obj.split(".a(", 1)[0].rsplit("/", 1)[-1] + ".a"
    else:
        archive = obj.rsplit("/", 1)[-1]
    totals[archive] += size
    symbols.append((size, obj))

print("== retained section bytes by archive/object ==")
for name, n in sorted(totals.items(), key=lambda x: x[1], reverse=True):
    print(f"{n:8d}  {name}")

print("\n== largest retained input sections ==")
for n, obj in sorted(symbols, reverse=True)[:80]:
    print(f"{n:8d}  {obj}")
