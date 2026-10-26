"""Provider request budget: a rolling-window governor.

Synthetic subscriptions meter REQUESTS per 5-hour window, not tokens, so the
scarce resource for a long campaign is request count. Every crew model call is
already one telemetry row with `requests: 1` (failures included), so the ledger
IS the meter: count rows inside the window and pace from that.

The governor answers two things:
  remaining()  how many requests are left right now (minus a reserve held back
               for Kris's own interactive work, which we cannot see)
  gate(n)      may a job that could spend n requests start, and if not, how
               long until enough of the window has aged out

It never guesses: an unreadable or missing ledger means "no evidence of spend",
which is reported as such rather than silently allowing an unbounded run.
"""

import datetime
import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple

DEFAULTS = {"mode": "bucket", "window_seconds": 5 * 3600, "max_requests": 500,
            "regen_percent": 5, "regen_hours": 3, "reserve": 50,
            "min_headroom": 4}


class RateWindow:
    def __init__(self, cfg):
        self.cfg = cfg
        self.settings = {**DEFAULTS, **(cfg.data.get("rate_limit") or {})}
        self.path = Path(os.environ.get("ATLAS_TELEMETRY_FILE")
                         or cfg.telemetry_file
                         or (Path(cfg.state_home) / "telemetry.jsonl"))

    # -- meter ----------------------------------------------------------------
    def _rows_in_window(self) -> int:
        if not self.path.exists():
            return 0
        cutoff = time.time() - self.settings["window_seconds"]
        used = 0
        try:
            with open(self.path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"requests"' not in line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = row.get("ts")
                    if not ts:
                        continue
                    try:
                        when = datetime.datetime.fromisoformat(ts).timestamp()
                    except ValueError:
                        continue
                    if when >= cutoff:
                        used += int(row.get("requests") or 0)
        except OSError:
            return 0
        return used

    def used(self) -> int:
        return self._rows_in_window()

    # -- bucket mode ----------------------------------------------------------
    # Kris's allowance refills 5% of capacity every 3 hours rather than
    # dropping requests out of a 5-hour window, so the honest model is a
    # token bucket. State lives next to the jobs so several crew processes
    # (and separate CLI runs) share one view of the level.
    @property
    def _state_path(self) -> Path:
        return Path(self.cfg.state_home) / "rate_state.json"

    def _regen_per_second(self) -> float:
        s = self.settings
        hours = max(float(s.get("regen_hours") or 3), 0.01)
        return s["max_requests"] * (float(s.get("regen_percent") or 5) / 100.0) / (hours * 3600.0)

    def _ledger_total(self) -> int:
        """Every request the harness has ever logged (monotonic counter)."""
        if not self.path.exists():
            return 0
        total = 0
        try:
            with open(self.path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"requests"' not in line:
                        continue
                    try:
                        total += int(json.loads(line).get("requests") or 0)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
        except OSError:
            return 0
        return total

    def _bucket_level(self, persist: bool = True) -> float:
        s = self.settings
        now = time.time()
        total = self._ledger_total()
        try:
            st = json.loads(self._state_path.read_text(encoding="utf-8"))
            level, then, seen = float(st["level"]), float(st["ts"]), int(st["ledger_total"])
        except (OSError, KeyError, ValueError, TypeError):
            # No state yet (first run, or Kris deleted it to reset): assume the
            # bucket was full before this window and charge only what was spent
            # inside it. Charging all history would zero a long-lived ledger;
            # charging nothing would ignore a spree that just happened.
            level = max(0.0, float(s["max_requests"]) - self._rows_in_window())
            then, seen = now, total
        spent = max(0, total - seen)              # requests since we last looked
        level = min(float(s["max_requests"]),
                    level + (now - then) * self._regen_per_second()) - spent
        level = max(0.0, level)
        if persist:
            try:
                self._state_path.parent.mkdir(parents=True, exist_ok=True)
                self._state_path.write_text(json.dumps(
                    {"level": round(level, 3), "ts": now, "ledger_total": total,
                     "note": "crew request bucket; delete to reset to full"}),
                    encoding="utf-8")
            except OSError:
                pass
        return level

    def remaining(self) -> int:
        s = self.settings
        if s.get("mode", "bucket") == "bucket":
            return max(0, int(self._bucket_level() - s["reserve"]))
        return max(0, s["max_requests"] - s["reserve"] - self.used())

    def seconds_for(self, requests: int) -> float:
        """How long until the bucket has room for `requests` more."""
        need = max(0.0, requests - self.remaining())
        rate = self._regen_per_second()
        return 0.0 if need <= 0 else need / rate

    def oldest_in_window_age(self) -> Optional[float]:
        """Seconds since the oldest request still inside the window, or None."""
        if not self.path.exists():
            return None
        cutoff = time.time() - self.settings["window_seconds"]
        oldest = None
        try:
            with open(self.path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"requests"' not in line:
                        continue
                    try:
                        row = json.loads(line)
                        when = datetime.datetime.fromisoformat(row["ts"]).timestamp()
                    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                        continue
                    if when >= cutoff and (oldest is None or when < oldest):
                        oldest = when
        except OSError:
            return None
        return None if oldest is None else time.time() - oldest

    # -- governor -------------------------------------------------------------
    # -- what the provider itself reports ------------------------------------
    #
    # Everything below this line beats everything above it. The bucket model was
    # a reasonable guess with no better information; a reading is not a guess.

    def provider_view(self):
        """The provider's own live account of what is left, or None."""
        try:
            import sys
            from .config import REPO_ROOT
            sys.path.insert(0, str(REPO_ROOT / "v3-service"))
            from providers import quotas
            return quotas.latest(), quotas
        except Exception:                                    # noqa: BLE001
            return None, None

    def provider_gate(self, want: int):
        """(ok, wait_seconds, detail) from the provider's numbers, or None when it
        has never answered us.

        Never raises. A header of a shape we did not expect must fall through to
        the bucket, not abort the worker loop: on 2026-10-24 a `None` formatted
        with `:.1f` raised on every tick and the crew looked idle for nine hours
        while its budget read healthy.
        """
        try:
            return self._provider_gate(want)
        except Exception:                                # noqa: BLE001
            return None

    def _provider_gate(self, want: int):
        """The provider's own numbers; `provider_gate` is the safe entry point."""
        view, quotas = self.provider_view()
        if not view:
            return None
        s = self.settings
        reserve_frac = float(s.get("credit_reserve_percent", 5)) / 100.0
        if view.get("requests_limited"):
            return (False, 900.0,
                    "the provider says the five-hour request limit is reached; "
                    f"next tick {view.get('requests_next_tick')}")
        remaining = view.get("requests_remaining")
        if remaining is not None and remaining < max(1.0, float(s.get("min_headroom", 4))):
            return (False, 900.0,
                    f"only {remaining:.1f} requests left in this five-hour window; "
                    f"next tick {view.get('requests_next_tick')}")
        percent = view.get("credits_percent_remaining")
        if percent is not None and percent / 100.0 <= reserve_frac:
            return (False, 3600.0,
                    f"weekly credits are down to {quotas.credits_text(view)}, below the "
                    f"{reserve_frac * 100:.0f}% reserve kept for interactive work. "
                    f"{quotas.regen_text(view)}")
        binding = quotas.binding_limit(view) if quotas else {}
        # Either number can be missing (2026-10-24: a header shape change left both
        # None and this line raised on every worker tick, so no job was claimed).
        requests = (f"{remaining:.1f}/{view.get('requests_max')}"
                    if remaining is not None else "? (not reported)")
        credits = f"{percent:.1f}%" if percent is not None else "? (not reported)"
        return (True, 0.0,
                f"provider reports {requests} requests and {credits} of weekly "
                f"credits; binding limit is {binding.get('limit', '?')}")

    def gate(self, job_requests: int = 0) -> Tuple[bool, float, str]:
        """(may_start, wait_seconds, detail). A job may start when the window
        has room for its whole budget, or at least min_headroom requests: a
        job stopped by the request budget mid-way still produced a partial
        result, which is better than never starting, but we never start with
        almost nothing left."""
        authoritative = self.provider_gate(job_requests)
        if authoritative is not None:
            return authoritative
        s = self.settings
        left = self.remaining()
        want = max(int(job_requests or 0), 1)
        if left >= want or left >= s["min_headroom"]:
            return True, 0.0, f"{left} of {s['max_requests']} requests available"
        if s.get("mode", "bucket") == "bucket":
            wait = max(60.0, self.seconds_for(s["min_headroom"]))
            return False, wait, (
                f"only {left} requests available (reserve {s['reserve']} held back); "
                f"refill of {s['min_headroom']} takes ~{int(wait / 60)} min at "
                f"{s['regen_percent']}% per {s['regen_hours']}h")
        age = self.oldest_in_window_age()
        wait = max(30.0, s["window_seconds"] - (age or 0)) if age is not None else 60.0
        return False, wait, (f"only {left} requests left (reserve {s['reserve']}); "
                             f"next window room in ~{int(wait / 60)} min")

    def report(self) -> dict:
        provider, quotas = self.provider_view()
        s = self.settings
        mode = s.get("mode", "bucket")
        out = {"provider_reported": provider,
               "binding_limit": (quotas.binding_limit(provider)
                                 if (provider and quotas) else None),
               "mode": mode + (" (fallback only: the provider's own reading wins)"
                               if provider else ""),
               "max_requests": s["max_requests"],
               "reserve_for_interactive_use": s["reserve"],
               "available_to_crew": self.remaining(),
               "used_in_last_window": self.used()}
        if mode == "bucket":
            per_hour = self._regen_per_second() * 3600
            out.update({"bucket_level": round(self._bucket_level(persist=False), 1),
                        "refill": f"{s['regen_percent']}% of {s['max_requests']} "
                                  f"every {s['regen_hours']}h "
                                  f"(~{per_hour:.1f} requests/hour)",
                        "hours_to_refill_100": round(100 / per_hour, 1) if per_hour else None,
                        "lifetime_requests_logged": self._ledger_total(),
                        "state": str(self._state_path)})
        else:
            age = self.oldest_in_window_age()
            out["oldest_request_age_min"] = round(age / 60, 1) if age else None
        out.update({"ledger": str(self.path),
                    "note": ("Counts every request the harness logged (crew, "
                             "battery, duties, OpenCode runs it wraps). Requests "
                             "Kris or Crush make outside the harness are invisible "
                             "here; that is what the reserve is for.")})
        return out
