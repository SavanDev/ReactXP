#!/usr/bin/env python3
"""
Measures how much of the NT API surface is still missing, straight from the
source tree (no reference binaries needed).

- Exports: parses every .spec file the way spec2def does for one target
  (architecture + NT version) and counts real exports vs stubs.
- Markers: counts UNIMPLEMENTED / STATUS_NOT_IMPLEMENTED style markers per
  component.

Usage: tools/parity-metrics.py [--version 0x502] [--arch i386]
                               [--markdown FILE] [--json FILE]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_DIRS = ["dll", "ntoskrnl", "hal", "win32ss", "drivers", "base"]
CODE_DIRS = ["ntoskrnl", "hal", "win32ss", "dll", "drivers", "base", "boot/freeldr"]
CODE_EXT = (".c", ".cpp", ".h", ".s", ".S")

# Modules whose completeness matters most for running XP-era software.
CORE = {
    "ntoskrnl", "hal", "ntdll", "kernel32", "advapi32", "user32", "gdi32",
    "win32k", "rpcrt4", "ole32", "oleaut32", "shell32", "shlwapi", "comctl32",
    "comdlg32", "msvcrt", "ws2_32", "secur32", "setupapi", "crypt32", "wininet",
    "netapi32", "winmm", "version", "userenv", "imm32", "usp10", "dbghelp",
    "iphlpapi", "mswsock", "cfgmgr32", "uxtheme", "winspool", "ntoskrnl_vista",
}

# Same word lists spec2def accepts as the export type.
CALL_TYPES = {"stdcall", "cdecl", "fastcall", "thiscall", "pascal", "varargs",
              "extern", "stub"}

MARKERS = {
    "UNIMPLEMENTED": re.compile(r"\bUNIMPLEMENTED(?:_ONCE|_DBGBREAK)?\b"),
    "STATUS_NOT_IMPLEMENTED": re.compile(r"\breturn\s*\(?\s*STATUS_NOT_IMPLEMENTED\b"),
    "ERROR_CALL_NOT_IMPLEMENTED": re.compile(r"\bERROR_CALL_NOT_IMPLEMENTED\b"),
    "E_NOTIMPL": re.compile(r"\breturn\s*\(?\s*E_NOTIMPL\b"),
}


def arch_aliases(arch):
    # spec2def matches the arch name and a "win32"/"win64" alias
    return {arch, "win64" if arch in ("x86_64", "arm64") else "win32"}


def included(opts, arch, version):
    """Reproduces spec2def's -arch / -i386 / -version filtering."""
    for opt in opts:
        if opt.startswith("-arch="):
            ok = False
            for a in opt[6:].split(","):
                neg = a.startswith("!")
                a = a.lstrip("!")
                if (a in arch_aliases(arch)) != neg:
                    ok = True
            if not ok:
                return False
        elif opt == "-i386" and arch != "i386":
            return False
        elif opt.startswith("-version="):
            ok = False
            for rng in opt[9:].split(","):
                if rng.endswith("+"):
                    lo, hi = int(rng[:-1], 16), 0xFFF
                elif "-" in rng:
                    lo, hi = (int(x, 16) for x in rng.split("-", 1))
                else:
                    lo = hi = int(rng, 16)
                if lo <= version <= hi:
                    ok = True
            if not ok:
                return False
    return True


def parse_spec(path, arch, version):
    total = stubs = 0
    stub_names = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line or not (line[0] == "@" or line[0].isdigit()):
                continue
            tok = line.split()
            if len(tok) < 2 or tok[1] not in CALL_TYPES:
                continue
            kind = tok[1]
            i = 2
            opts = []
            while i < len(tok) and tok[i].startswith("-"):
                opts.append(tok[i])
                i += 1
            if not included(opts, arch, version):
                continue
            name = tok[i].split("(", 1)[0] if i < len(tok) else "?"
            total += 1
            if kind == "stub" or "-stub" in opts:
                stubs += 1
                stub_names.append(name)
    return total, stubs, stub_names


def scan_exports(arch, version):
    modules = {}
    for top in SPEC_DIRS:
        for dirpath, dirnames, files in os.walk(os.path.join(ROOT, top)):
            dirnames.sort()
            for fn in sorted(files):
                if not fn.endswith(".spec"):
                    continue
                path = os.path.join(dirpath, fn)
                total, stubs, names = parse_spec(path, arch, version)
                if total == 0:
                    continue
                mod = fn[:-5]
                modules[mod] = {
                    "path": os.path.relpath(path, ROOT),
                    "exports": total,
                    "stubs": stubs,
                    "stub_names": names,
                }
    return modules


def component_of(rel):
    parts = rel.split(os.sep)
    if parts[0] in ("dll", "drivers", "base", "win32ss") and len(parts) > 3:
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def scan_markers():
    per_comp = {}
    totals = Counter()
    for top in CODE_DIRS:
        for dirpath, dirnames, files in os.walk(os.path.join(ROOT, top)):
            dirnames.sort()
            for fn in files:
                if not fn.endswith(CODE_EXT):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, ROOT)
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                counts = Counter()
                for line in text.splitlines():
                    if line.lstrip().startswith("#define"):
                        continue
                    for key, rx in MARKERS.items():
                        counts[key] += len(rx.findall(line))
                if not +counts:
                    continue
                comp = component_of(rel)
                per_comp.setdefault(comp, Counter()).update(counts)
                totals.update(counts)
    return per_comp, totals


def pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


def markdown(report, top_n):
    v, a = report["target"]["version"], report["target"]["arch"]
    mods = report["exports"]
    out = [f"# Métricas de paridad NT ({v}, {a})", ""]

    def summary_row(label, sel):
        e = sum(m["exports"] for m in sel)
        s = sum(m["stubs"] for m in sel)
        return f"| {label} | {len(sel)} | {e} | {s} | {pct(e - s, e):.1f} % |"

    core = [m for k, m in mods.items() if k in CORE]
    out += ["## Exportaciones", "",
            "| Conjunto | Módulos | Exportaciones | Stubs | Implementado |",
            "|---|---:|---:|---:|---:|",
            summary_row("Núcleo", core),
            summary_row("Todo", list(mods.values())), ""]

    def table(title, items):
        rows = [f"### {title}", "",
                "| Módulo | Exportaciones | Stubs | Implementado |",
                "|---|---:|---:|---:|"]
        for name, m in items:
            rows.append(f"| {name} | {m['exports']} | {m['stubs']} | "
                        f"{pct(m['exports'] - m['stubs'], m['exports']):.1f} % |")
        return rows + [""]

    core_items = sorted(((k, m) for k, m in mods.items() if k in CORE),
                        key=lambda kv: -kv[1]["stubs"])
    out += table("Núcleo, por stubs pendientes", core_items)
    worst = sorted(mods.items(), key=lambda kv: -kv[1]["stubs"])[:top_n]
    out += table(f"Top {top_n} módulos con más stubs", worst)

    t = report["markers_total"]
    out += ["## Marcadores en el código", "",
            "| Marcador | Cantidad |", "|---|---:|"]
    out += [f"| `{k}` | {t.get(k, 0)} |" for k in MARKERS]
    # E_NOTIMPL is mostly unimplemented COM methods in Wine code; it would
    # drown everything else, so it is shown but not used for ranking.
    def nt_total(c):
        return sum(v for k, v in c.items() if k != "E_NOTIMPL")

    out += ["", f"### Top {top_n} componentes (ordenado sin `E_NOTIMPL`)", "",
            "| Componente | " + " | ".join(f"`{k}`" for k in MARKERS) + " | Total NT |",
            "|---|" + "---:|" * (len(MARKERS) + 1)]
    comps = sorted(report["markers"].items(), key=lambda kv: -nt_total(kv[1]))
    for comp, c in comps[:top_n]:
        out.append(f"| {comp} | " + " | ".join(str(c.get(k, 0)) for k in MARKERS)
                   + f" | {nt_total(c)} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="0x502", help="NT version (hex), default 0x502")
    ap.add_argument("--arch", default="i386")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--markdown", help="write a Markdown report here ('-' = stdout)")
    ap.add_argument("--json", help="write the full data (incl. stub names) here")
    args = ap.parse_args()

    version = int(args.version, 16)
    exports = scan_exports(args.arch, version)
    per_comp, totals = scan_markers()
    report = {
        "target": {"version": f"0x{version:03X}", "arch": args.arch},
        "exports": exports,
        "markers": {k: dict(v) for k, v in per_comp.items()},
        "markers_total": dict(totals),
    }
    core = [m for k, m in exports.items() if k in CORE]
    report["summary"] = {
        "core_exports": sum(m["exports"] for m in core),
        "core_stubs": sum(m["stubs"] for m in core),
        "all_exports": sum(m["exports"] for m in exports.values()),
        "all_stubs": sum(m["stubs"] for m in exports.values()),
    }

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, sort_keys=True)
    md = markdown(report, args.top)
    if args.markdown == "-" or not (args.markdown or args.json):
        sys.stdout.write(md)
    elif args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    main()
