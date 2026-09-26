"""Timed run: spread planned crew work over a window, and test whether we can
forecast what it costs.

Kris, 2026-09-25: "stretch the jobs to last [until the reset] ... lets test if
we can time our usage well enough to plan reliably on its availability and our
skills at using the models efficiently."

Each plan item has a planned start (minutes from the run's start), a kind
(campaign | job | command) and a PREDICTION (tokens, minutes). The runner:

- waits for the planned time (status.json says what it is waiting for);
- reads the provider's own balance before and after (providers.quotas.latest -
  Synthetic reports it on every response; our own model of it was once 30x wrong);
- measures tokens from the telemetry ledger for the item's window;
- allows for credit REGENERATION (+$ every N minutes at the provider's stated
  next time), which otherwise makes "before minus after" meaningless;
- re-calibrates $/1k tokens from what it has seen so far and re-forecasts the
  balance at the deadline after every item. The report compares the first
  forecast, the running forecasts and the truth.

  python C:/Users/user/ATLAS-api-harness/crew/runners/timed_run.py PLAN.json
"""

import datetime as dt
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "v3-service"))

from crew.config import load_config  # noqa: E402

LEDGER = Path("C:/Users/user/Documents/Obsidian/Knowledge_Base/wiki/experiments/"
              "atlas-api-harness/runs/telemetry.jsonl")


def now():
    return dt.datetime.now()


def stamp(t=None):
    return (t or now()).strftime("%Y-%m-%dT%H:%M:%S")


def reading():
    """The provider's last balance reading, or {} if none yet."""
    try:
        from providers.quotas import latest
        return latest() or {}
    except Exception:  # noqa: BLE001
        return {}


def ledger_tokens(start: str, end: str) -> dict:
    out = {"tokens": 0, "calls": 0, "by_model": {}}
    try:
        lines = LEDGER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines[-20000:]:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if start <= e.get("ts", "") <= end:
            t = int(e.get("total_tokens") or 0)
            out["tokens"] += t
            out["calls"] += 1
            m = e.get("model", "?")
            out["by_model"][m] = out["by_model"].get(m, 0) + t
    return out


def _utc_to_local(s: str):
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.astimezone().replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def regen_between(r: dict, a: dt.datetime, b: dt.datetime, period_min: float) -> float:
    """Credits the provider adds between a and b, from its stated next regen."""
    nxt = _utc_to_local(r.get("credits_next_regen_at", ""))
    amt = float(r.get("credits_next_regen_usd") or 0)
    if not nxt or not amt:
        return 0.0
    total, t = 0.0, nxt
    while t <= b:
        if t > a:
            total += amt
        t += dt.timedelta(minutes=period_min)
    return total


class Runner:
    def __init__(self, plan: dict):
        self.plan = plan
        self.cfg = load_config()
        self.home = Path(self.cfg.state_home) / "timed" / plan["name"]
        self.home.mkdir(parents=True, exist_ok=True)
        self.start = now()
        self.deadline = dt.datetime.fromisoformat(plan["deadline"])
        self.rate = float(plan.get("prior_usd_per_1k_tokens", 0.0042))
        self.period = float(plan.get("regen_period_minutes", 202))
        self.items = [dict(i, state="planned") for i in plan["items"]]
        self.first_forecast = None
        self.forecasts = []

    # -- bookkeeping -------------------------------------------------------------
    def log(self, text):
        line = f"{stamp()} {text}"
        print(line, flush=True)
        with open(self.home / "progress.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def forecast(self) -> dict:
        r = reading()
        bal = float(r.get("credits_remaining_usd") or 0)
        left = [i for i in self.items if i["state"] in ("planned", "waiting", "running")]
        spend = sum(i["predict"]["tokens"] * self.rate / 1000 *
                    float(i["predict"].get("price_factor", 1.0)) for i in left)
        regen = regen_between(r, now(), self.deadline, self.period)
        f = {"at": stamp(), "balance_now": round(bal, 3), "usd_per_1k": round(self.rate, 5),
             "predicted_spend_left": round(spend, 3), "regen_left": round(regen, 3),
             "balance_at_deadline": round(bal - spend + regen, 3)}
        return f

    def status(self, current=None, waiting_until=None):
        s = {"name": self.plan["name"], "started": stamp(self.start),
             "deadline": stamp(self.deadline), "now": stamp(),
             "current": current, "waiting_until": waiting_until,
             "rate_usd_per_1k": round(self.rate, 5),
             "first_forecast": self.first_forecast,
             "latest_forecast": self.forecasts[-1] if self.forecasts else None,
             "items": [{k: i.get(k) for k in ("id", "state", "planned_at", "started",
                                              "finished", "predict", "actual", "error")}
                       for i in self.items]}
        (self.home / "status.json").write_text(json.dumps(s, indent=1), encoding="utf-8")

    # -- running -----------------------------------------------------------------
    def run_item(self, item) -> dict:
        kind = item["kind"]
        if kind == "campaign":
            from crew.campaign import Campaign, load
            return {"campaign": Campaign(load(item["file"]), quiet=True).run()}
        if kind == "job":
            from crew.config import load_config as _lc
            from crew.core import Crew
            crew = Crew(_lc())
            spec = json.loads(Path(item["spec"]).read_text(encoding="utf-8"))
            brief = crew.submit(spec, "Claude", claim=True)
            try:
                crew.run_job(brief["task_id"])
            finally:
                crew.store.release(brief["task_id"])
            r = crew.result(brief["task_id"])
            return {k: r.get(k) for k in ("task_id", "assigned_to", "status",
                                          "passed_gates", "requests", "tokens")}
        if kind == "command":
            argv = item["argv"]
            if item.get("requires") and not Path(item["requires"]).exists():
                raise RuntimeError(f"not ready: {item['requires']} does not exist")
            p = subprocess.run(argv, capture_output=True, text=True, cwd=str(REPO),
                               timeout=int(item.get("timeout_s", 3600)),
                               encoding="utf-8", errors="replace")
            (self.home / f"{item['id']}.out.txt").write_text(p.stdout + p.stderr,
                                                             encoding="utf-8")
            return {"exit": p.returncode, "tail": (p.stdout + p.stderr)[-400:]}
        raise ValueError(f"unknown kind {kind}")

    def run(self):
        self.first_forecast = self.forecast()
        self.forecasts.append(self.first_forecast)
        self.log(f"start; first forecast {self.first_forecast}")
        spent_usd = spent_tokens = 0.0
        for item in self.items:
            planned = self.start + dt.timedelta(minutes=float(item["at_min"]))
            item["planned_at"] = stamp(planned)
            item["state"] = "waiting"
            while now() < planned:
                self.status(item["id"], stamp(planned))
                time.sleep(min(30, max(1, (planned - now()).total_seconds())))
            item["state"], item["started"] = "running", stamp()
            self.status(item["id"])
            self.log(f"run {item['id']} (planned {item['planned_at']})")
            before, t0 = reading(), now()
            try:
                item["result"] = self.run_item(item)
            except Exception as e:  # noqa: BLE001 - one item never stops the run
                item["error"] = f"{type(e).__name__}: {e}"
                (self.home / f"{item['id']}.error.txt").write_text(
                    traceback.format_exc(), encoding="utf-8")
            t1, after = now(), reading()
            item["finished"], item["state"] = stamp(t1), ("failed" if item.get("error") else "done")
            led = ledger_tokens(stamp(t0), stamp(t1))
            # The balance only updates when a call is made, so the "before"
            # reading can be old: count regeneration from WHEN IT WAS READ, not
            # from the job's start. (2026-09-25: a regen landed between an 08:02
            # reading and an 08:25 job, which then "cost" -$0.95.)
            read_at = before.get("read_at")
            since = dt.datetime.fromisoformat(read_at) if read_at else t0
            regen = regen_between(before, since, t1, self.period)
            b0 = float(before.get("credits_remaining_usd") or 0)
            b1 = float(after.get("credits_remaining_usd") or 0)
            usd = round(b0 - b1 + regen, 4) if before and after else None
            item["actual"] = {"tokens": led["tokens"], "calls": led["calls"],
                              "usd": usd, "regen_in_window": regen,
                              "minutes": round((t1 - t0).total_seconds() / 60, 1),
                              "by_model": led["by_model"],
                              "reading_after": after.get("read_at")}
            if usd is not None and led["tokens"]:
                spent_usd += usd * 1.0 / float(item["predict"].get("price_factor", 1.0))
                spent_tokens += led["tokens"]
                if spent_tokens > 0 and spent_usd > 0:
                    self.rate = spent_usd / spent_tokens * 1000
            self.forecasts.append(self.forecast())
            self.log(f"done {item['id']}: {item['actual']} err={item.get('error')}; "
                     f"forecast {self.forecasts[-1]}")
            self.status()
        self.report()

    def report(self):
        final = reading()
        truth = float(final.get("credits_remaining_usd") or 0)
        rows = ["| item | planned | started | minutes (pred / actual) | tokens (pred / actual) | $ actual | outcome |",
                "|---|---|---|---|---|---|---|"]
        for i in self.items:
            a = i.get("actual") or {}
            res = i.get("result") or {}
            outcome = i.get("error") or res.get("status") or \
                (res.get("campaign") or {}).get("outcome") or res.get("exit")
            rows.append(f"| {i['id']} | {i.get('planned_at', '')[11:16]} | "
                        f"{(i.get('started') or '')[11:16]} | {i['predict'].get('minutes')} / "
                        f"{a.get('minutes')} | {i['predict']['tokens']:,} / {a.get('tokens', 0):,} | "
                        f"{a.get('usd')} | {outcome} |")
        fc = ["| at | balance then | $/1k | forecast balance at deadline |", "|---|---|---|---|"]
        for f in self.forecasts:
            fc.append(f"| {f['at'][11:16]} | {f['balance_now']} | {f['usd_per_1k']} | "
                      f"{f['balance_at_deadline']} |")
        text = "\n".join([
            f"# Timed run: {self.plan['name']}", "",
            f"Window {stamp(self.start)} -> deadline {stamp(self.deadline)}; ended {stamp()}.",
            f"Balance at the end (provider reading {final.get('read_at')}): ${truth}.",
            f"First forecast for the deadline: ${self.first_forecast['balance_at_deadline']}; "
            f"last: ${self.forecasts[-1]['balance_at_deadline']}.", "",
            "## Items", *rows, "", "## Forecasts after each item", *fc, ""])
        (self.home / "REPORT.md").write_text(text, encoding="utf-8")
        self.status()
        self.log(f"report written: {self.home / 'REPORT.md'}")


if __name__ == "__main__":
    Runner(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))).run()
