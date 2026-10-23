"""Night shift: at 3 AM, sort the day's crew failures and write NIGHT_REPORT.md.

Kris, 2026-10-23: "Reasons for failures are evaluated at end of work day (around 3AM)
and programs are written to eliminate simple issues that can be automated." His choice
was zero tokens: this script only reads what the harness already wrote and sorts it
with the crew-built night_signatures.py. In the morning the PA turns repeated mechanical
failures into fixer jobs (contract, hidden tests, crew build, Unify order); nothing here
changes the crew or its gates.

Reads, for the last --hours (default 24):
  runs/crew/jobs/*/job.json           failed jobs -> categories and signatures
  runs/crew/campaigns/*/status.json   relays and outcomes per campaign
  runs/guard/hits.jsonl               the Windows command guard's rewrites and blocks
Writes runs/crew/night/NIGHT_REPORT-<date>.md, NIGHT_REPORT.md (always the latest) and
night-<date>.json. --notify shows a Windows notification with the headline.

  python C:/Users/user/ATLAS-api-harness/crew/runners/night_shift.py [--hours 24] [--notify]
"""

import argparse
import base64
import collections
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

GUARD_LOG = REPO / "runs" / "guard" / "hits.jsonl"

# Windows PowerShell 5.1 still projects the WinRT toast types; pwsh 7 does not.
_TOAST = r"""
$ErrorActionPreference = 'Stop'
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $x.GetElementsByTagName('text')
[void]$t.Item(0).AppendChild($x.CreateTextNode($env:NIGHT_TITLE))
[void]$t.Item(1).AppendChild($x.CreateTextNode($env:NIGHT_BODY))
$n = [Windows.UI.Notifications.ToastNotification]::new($x)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show($n)
"""


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _recent(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime >= cutoff
    except OSError:
        return False


def failed_jobs(state: Path, cutoff: float) -> list:
    jobs = []
    for path in sorted((state / "jobs").glob("*/job.json")):
        if _recent(path, cutoff):
            job = _read_json(path)
            if job and job.get("status") == "failed":
                jobs.append(job)
    return jobs


def campaigns(state: Path, cutoff: float) -> list:
    out = []
    for path in sorted((state / "campaigns").glob("*/status.json")):
        if not _recent(path, cutoff):
            continue
        status = _read_json(path) or {}
        relays = [{"task": tid, **r} for tid, t in (status.get("tasks") or {}).items()
                  for r in t.get("relays") or []]
        out.append({"campaign": status.get("campaign") or path.parent.name,
                    "counts": status.get("counts") or {},
                    "requests": status.get("requests_used"), "relays": relays,
                    "finished": (path.parent / "summary.json").exists()})
    return out


def guard_hits(cutoff: float) -> dict:
    """{action: Counter(note)} from the guard's log; empty when the guard has not run."""
    hits = collections.defaultdict(collections.Counter)
    if not GUARD_LOG.is_file():
        return {}
    for line in GUARD_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            hit = json.loads(line)
            if float(hit.get("epoch", 0)) < cutoff:     # winguard-hook writes epoch seconds
                continue
        except (ValueError, TypeError):
            continue
        for note in hit.get("notes") or ["(no note)"]:
            hits[str(hit.get("action", "?")).lower()][note] += 1
    return {k: dict(v) for k, v in hits.items()}


def _table(rows: list, header: list) -> list:
    if not rows:
        return ["(none)"]
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows])


def report(groups: list, camps: list, guard: dict, signatures, hours: int,
           threshold: int, now: dt.datetime) -> tuple:
    failed_jobs_n = len({j for g in groups for j in g["job_ids"]})
    candidates = [g for g in groups if g["candidate"]]
    relays = [r for c in camps for r in c["relays"]]
    rewrites = sum(guard.get("rewrite", {}).values())
    blocks = sum(guard.get("block", {}).values())
    headline = (f"{failed_jobs_n} failed job(s) in {len(groups)} group(s); "
                f"{len(candidates)} fixer candidate(s); {len(relays)} relay(s); "
                f"guard: {rewrites} rewrite(s), {blocks} block(s)")
    md = [f"# Night report - {now:%Y-%m-%d %H:%M}", "",
          f"Window: the last {hours} h. Zero tokens: sorted by night_signatures.py from what "
          f"the harness wrote.", "", f"**{headline}**", "",
          f"## Fixer candidates (mechanical, seen {threshold}+ times)", ""]
    md += _table([[g["count"], g["signature"], ", ".join(g["members"]), g["job_ids"][0]]
                  for g in candidates], ["count", "signature", "members", "example job"])
    md += ["", "## Failures by category"]
    by_cat = collections.OrderedDict()
    for g in groups:
        by_cat.setdefault(g["category"], []).append(g)
    if not by_cat:
        md += ["", "(no failed jobs in the window)"]
    for cat, items in by_cat.items():
        md += ["", f"### {cat} ({sum(g['count'] for g in items)}) - {signatures.advice(cat)}", ""]
        md += _table([[g["count"], g["signature"], ", ".join(g["members"]),
                       ", ".join(g["job_ids"][:3]) + (" ..." if len(g["job_ids"]) > 3 else "")]
                      for g in items], ["count", "signature", "members", "jobs"])
    md += ["", "## Relays (work passed to the next capable member)", ""]
    md += _table([[r["task"], f"{r['from']} -> {r['to']}", r.get("reason", "")] for r in relays],
                 ["task", "from -> to", "reason"])
    md += ["", "## Campaigns touched", ""]
    md += _table([[c["campaign"], c["counts"].get("accepted", 0), c["counts"].get("failed", 0),
                   c["counts"].get("running", 0) + c["counts"].get("waiting", 0),
                   c["requests"], "finished" if c["finished"] else "open"] for c in camps],
                 ["campaign", "accepted", "failed", "open tasks", "requests", "state"])
    md += ["", "## Windows command guard", ""]
    md += _table([[action, n, note] for action, notes in sorted(guard.items())
                  for note, n in sorted(notes.items(), key=lambda kv: -kv[1])],
                 ["action", "count", "note"])
    md += ["", "## For the morning (PA)", "",
           "- Each fixer candidate: write a contract and hidden tests for a zero-token fixer "
           "(autofix / quirklint), let the crew build it, and keep Kris's Unify order "
           "before it goes live.",
           "- ceiling groups: check the member's budget in personnel.json before blaming them.",
           "- guard blocks seen often: consider a certain rewrite for them.", ""]
    data = {"generated": now.isoformat(timespec="seconds"), "window_hours": hours,
            "headline": headline, "groups": groups, "relays": relays, "campaigns": camps,
            "guard": guard}
    return headline, "\n".join(md), data


def notify(title: str, body: str) -> bool:
    import os
    script = base64.b64encode(_TOAST.encode("utf-16-le")).decode("ascii")
    env = {**os.environ, "NIGHT_TITLE": title, "NIGHT_BODY": body}
    try:
        # no console window: the scheduled run is windowless (pythonw) at 3 AM
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                               "-EncodedCommand", script], env=env, capture_output=True,
                              timeout=60, creationflags=getattr(subprocess,
                                                                "CREATE_NO_WINDOW", 0))
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--threshold", type=int, default=3,
                    help="a mechanical signature seen this often becomes a fixer candidate")
    ap.add_argument("--out", help="folder for the report (default runs/crew/night)")
    ap.add_argument("--notify", action="store_true", help="show a Windows notification")
    args = ap.parse_args(argv)

    from crew import night_signatures as signatures
    from crew.config import load_config
    state = Path(load_config().state_home)
    out = Path(args.out) if args.out else state / "night"
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    cutoff = (now - dt.timedelta(hours=args.hours)).timestamp()

    def log(line: str) -> None:
        # the scheduled run has no console, so every run leaves one line here
        with (out / "night_shift.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {line}\n")

    try:
        groups = signatures.group(failed_jobs(state, cutoff), args.threshold)
        headline, md, data = report(groups, campaigns(state, cutoff), guard_hits(cutoff),
                                    signatures, args.hours, args.threshold, now)
        stamp = f"{now:%Y-%m-%d}"
        (out / f"NIGHT_REPORT-{stamp}.md").write_text(md, encoding="utf-8")
        (out / "NIGHT_REPORT.md").write_text(md, encoding="utf-8")
        (out / f"night-{stamp}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:                                      # noqa: BLE001
        log(f"FAILED {type(e).__name__}: {e}")
        if args.notify:
            notify("The Crew - night shift FAILED", f"{type(e).__name__}: {e}"[:200])
        raise
    log(headline)
    print(headline)
    print(f"report: {out / 'NIGHT_REPORT.md'}")
    if args.notify:
        shown = notify("The Crew - night report", f"{headline}. {out / 'NIGHT_REPORT.md'}")
        log("notification shown" if shown else "notification could not be shown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
