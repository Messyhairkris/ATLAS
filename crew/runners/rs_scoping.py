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
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGNS = ROOT / "crew" / "campaigns"
STATE = ROOT / "runs" / "crew" / "campaigns"

ATTEMPT = re.compile(r"\] (\S+): attempt \d+ by (\S+) \(team")
FAILED = re.compile(r"\] (\S+): failed - (.*)")


def history(log: Path):
    """(task, member) -> [attempt count, failure texts], from progress.log. A task can be
    resumed or reassigned, so the member is read from each 'attempt N by M' line - the
    status file keeps only the member who has it now."""
    seen = defaultdict(lambda: [0, []])
    current = {}
    if not log.is_file():
        return seen
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if m := ATTEMPT.search(line):
            current[m.group(1)] = m.group(2)
            seen[(m.group(1), m.group(2))][0] += 1
        elif (m := FAILED.search(line)) and m.group(1) in current:
            seen[(m.group(1), current[m.group(1)])][1].append(m.group(2)[:90])
    return seen


def rows(prefix: str):
    out = []
    for spec_path in sorted(CAMPAIGNS.glob(f"{prefix}*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        status_path = STATE / spec["name"] / "status.json"
        if not status_path.is_file():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        scope = {t["id"]: t.get("scope", "?") for t in spec["tasks"]}
        seen = history(STATE / spec["name"] / "progress.log")
        for tid, t in status["tasks"].items():
            base = tid[:-len("-tests")] if tid.endswith("-tests") else tid
            role = "tests" if t["kind"] == "tests" else "author"
            out.append({
                "campaign": spec["name"], "task": tid, "member": t["member"],
                "role": role, "scope": scope.get(base, "?"), "state": t["state"],
                "attempts": t["attempts"], "requests": t["requests"],
                "tokens": t["tokens"], "minutes": round(t["seconds"] / 60, 1),
                "first_failure": (seen[(tid, t["member"])][1] or [""])[0],
            })
            # Members who had this task before it was reassigned (their numbers are not
            # in the status file; the attempts and failures are from progress.log).
            for (task, member), (attempts, fails) in seen.items():
                if task == tid and member != t["member"]:
                    out.append({
                        "campaign": spec["name"], "task": tid, "member": member,
                        "role": role, "scope": scope.get(base, "?"),
                        # No failure of their own: stopped by the PA (provider stall).
                        "state": "reassigned" if fails else "stopped (provider)",
                        "attempts": attempts, "requests": "-", "tokens": "-",
                        "minutes": "-", "first_failure": (fails or [""])[0],
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
        if r["state"] != "stopped (provider)":   # not the member's doing
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
                     f"{sum(r['requests'] for r in rs if isinstance(r['requests'], int))} | "
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
