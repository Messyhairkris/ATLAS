"""What each member did on the Rust campaigns, by scope - the evidence for "which
scope suits whom" (Kris, 2026-10-20).

    python crew/runners/rs_scoping.py [--prefix pt_] [--out FILE]

Reads the campaign specs (crew/campaigns/<prefix>*.json, where each task carries a
`scope`: S small, M exact/byte-exact, L largest algorithm, C crate-facing with the API
card) and their live state (runs/crew/campaigns/<name>/status.json and events). Prints
one row per job and a per-member summary. Numbers are copied from the status files;
nothing is estimated.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGNS = ROOT / "crew" / "campaigns"
STATE = ROOT / "runs" / "crew" / "campaigns"


def rows(prefix: str):
    out = []
    for spec_path in sorted(CAMPAIGNS.glob(f"{prefix}*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        status_path = STATE / spec["name"] / "status.json"
        if not status_path.is_file():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        scope = {t["id"]: t.get("scope", "?") for t in spec["tasks"]}
        failures = defaultdict(list)
        for ev in status.get("events", []):
            if ev.get("event") == "task_failed_attempt":
                failures[ev["task"]].append((ev.get("gates") or ["?"])[0][:90])
        for tid, t in status["tasks"].items():
            base = tid[:-len("-tests")] if tid.endswith("-tests") else tid
            out.append({
                "campaign": spec["name"], "task": tid, "member": t["member"],
                "role": "tests" if t["kind"] == "tests" else "author",
                "scope": scope.get(base, "?"), "state": t["state"],
                "attempts": t["attempts"], "requests": t["requests"],
                "tokens": t["tokens"], "minutes": round(t["seconds"] / 60, 1),
                "first_failure": (failures.get(tid) or [""])[0],
            })
    return out


def render(data) -> str:
    lines = ["| member | role | scope | task | state | attempts | requests | tokens | min | first failure |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(data, key=lambda r: (r["member"], r["role"], r["scope"], r["task"])):
        lines.append(f"| {r['member']} | {r['role']} | {r['scope']} | {r['task']} | "
                     f"{r['state']} | {r['attempts']} | {r['requests']} | {r['tokens']} | "
                     f"{r['minutes']} | {r['first_failure']} |")
    lines += ["", "| member | accepted / jobs | first try | requests | by scope (accepted/jobs) |",
              "|---|---|---|---|---|"]
    by = defaultdict(list)
    for r in data:
        by[r["member"]].append(r)
    for m, rs in sorted(by.items()):
        acc = [r for r in rs if r["state"] == "accepted"]
        first = [r for r in acc if r["attempts"] == 1]
        scopes = defaultdict(lambda: [0, 0])
        for r in rs:
            key = f"{r['scope']}{'t' if r['role'] == 'tests' else ''}"
            scopes[key][1] += 1
            scopes[key][0] += r["state"] == "accepted"
        lines.append(f"| {m} | {len(acc)}/{len(rs)} | {len(first)} | "
                     f"{sum(r['requests'] for r in rs)} | "
                     + ", ".join(f"{k} {a}/{n}" for k, (a, n) in sorted(scopes.items()))
                     + " |")
    lines.append("")
    lines.append("Scope keys: S small, M exact or byte-exact, L largest algorithm, C crate-facing "
                 "with the API card; a trailing t means the member wrote the tests for it.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="pt_")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    text = render(rows(a.prefix))
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
