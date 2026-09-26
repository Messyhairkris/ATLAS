"""Special teams: a capable member (Kimi) driving real tools through NATIVE
tool calling, inside a harness that decides what it may touch.

Why a separate harness: Kimi-K3 abandoned the crew's plain-text tool protocol
in 5 of 5 jobs (Inspector dry run, 2026-09-25) - it wants native tool calls -
and it is publicly known for a 51% hallucination rate and "excessive
proactiveness". So:

- the harness, not the member, is the MCP client (crew/mcp_client.py); the
  member sees only the tools the mission allows, never run_code/evaluate/upload;
- every call is parsed and schema-checked first (st_schema.py, crew-built) and
  then checked against the mission (st_mission.py, crew-built): allowed tool,
  URL allowlist, step and action budgets, repeats. Refusals go back to the
  member as the tool result, with the reason;
- acting calls (click, type, key) are highlighted orange #FF7900 for half a
  second first and screenshotted (Kris's visible-progress rule);
- a hard credit cap reads the provider's own balance between steps;
- the final answer is graded: every `quoted` span must appear in something a
  tool actually returned, and the mission's expected observations must have
  been seen - Kimi's hallucination rate is the reason.

  python C:/Users/user/ATLAS-api-harness/crew/special_teams.py MISSION.json
"""

import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "v3-service"))

from crew.mcp_client import McpClient, McpError  # noqa: E402

WORKSPACE = REPO / "runs" / "crew" / "outbox" / "workspace" / "special_teams"
OUT_HOME = REPO / "runs" / "crew" / "special_teams"
PLAYWRIGHT = ["node", "C:/Users/user/playwright-mcp-setup/node_modules/@playwright/mcp/cli.js",
              "--headless", "--isolated", "--browser", "chromium",
              # the 5s default timed out a click that DID happen (dry run 2026-09-25)
              "--timeout-action", "15000"]
NEVER = {"browser_run_code_unsafe", "browser_evaluate", "browser_file_upload", "browser_drop",
         "browser_tabs", "browser_handle_dialog", "browser_close", "browser_resize",
         "browser_network_request", "browser_network_requests"}
ORANGE = "(el) => { el.style.outline = '3px solid #FF7900'; el.style.outlineOffset = '2px'; }"
UNHIGHLIGHT = "(el) => { el.style.outline = ''; }"
KEEP_FULL = 1            # tool results kept in full (the latest snapshot); older ones shrink
OLD_CHARS = 700
MAX_RESULT_CHARS = 30000
# pair backticks first, filter by length after (the gates.py bug, 2026-09-25)
QUOTE = re.compile(r"`([^`\n]+)`")


def _load_crew_module(name: str):
    """The crew-built module, from the workspace where the campaign accepted it."""
    path = WORKSPACE / f"{name}.py"
    if not path.is_file():
        raise SystemExit(f"{path} does not exist yet: the special-teams campaign has not "
                         f"accepted {name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _balance():
    try:
        from providers.quotas import latest
        return float((latest() or {}).get("credits_remaining_usd") or 0) or None
    except Exception:  # noqa: BLE001
        return None


def default_chat(member: str, reply_tokens: int):
    """Native tool calling through the same client (telemetry, quota header)
    the crew uses; tools ride in extra_body."""
    from providers.registry import resolve_alias
    from stages.llm_client import chat_completion
    os.environ.setdefault("ATLAS_PROVIDER", "synthetic")
    model = resolve_alias("synthetic", member)

    def chat(messages, tools, tool_choice="auto"):
        os.environ["ATLAS_CHAT_MODEL"] = model
        # Moonshot: agentic results at temperature 1.0, top-p 1.0 (Kimi K3 README)
        return chat_completion("", messages=messages, max_tokens=reply_tokens,
                               temperature=1.0,
                               extra_body={"tools": tools, "tool_choice": tool_choice,
                                           "top_p": 1.0})
    return chat


def _shrink(messages, context_chars=None):
    """Shorten old tool results. A browser mission needs only the latest page
    snapshot (KEEP_FULL); a file mission needs what it has read, so with a
    context budget the newest results stay whole until the budget is reached,
    oldest shortened first. (2026-09-25: keeping only the latest result made
    Kimi re-read special_teams.py 20 times in a review and never answer.)"""
    results = [m for m in messages if m.get("role") == "tool"]
    if context_chars:
        total = sum(len(str(m.get("content") or "")) for m in messages)
        for m in results[:-KEEP_FULL]:
            if total <= context_chars:
                return
            if len(m["content"]) > OLD_CHARS and not m.get("_short"):
                total -= len(m["content"]) - OLD_CHARS
                m["content"] = m["content"][:OLD_CHARS] + "\n...[older result shortened]"
                m["_short"] = True
        return
    for m in results[:-KEEP_FULL]:
        if len(m["content"]) > OLD_CHARS and not m.get("_short"):
            m["content"] = m["content"][:OLD_CHARS] + "\n...[older result shortened]"
            m["_short"] = True


CITE = re.compile(r"([\w./\\-]+\.(?:py|md|json)):(\d+)")


def _local_checks(mission: dict, final: str, out_dir: Path, provider) -> list:
    """Checks for file missions. A campaign design must leave its files staged and
    its reference passing its own hidden tests under the airlock; a review's
    every file:line must exist."""
    checks = []
    staged = out_dir / "staged"
    for rel in mission.get("expect_staged", []):
        checks.append({"check": f"staged {rel}", "ok": (staged / rel).is_file(),
                       "detail": "" if (staged / rel).is_file() else "not staged"})
    pair = mission.get("expect_green")
    if pair:
        runs = [c for c in getattr(provider, "checks", [])
                if c["module"] == pair["module"] and c["tests"] == pair["tests"]]
        last = runs[-1] if runs else None
        # re-run on the FINAL staged files: a green check before a later edit proves nothing
        if last is not None and hasattr(provider, "_check"):
            try:
                provider._check(pair)
                last = provider.checks[-1]
            except Exception as e:  # noqa: BLE001 - a missing file is a failed check
                last = {"ok": False, "steps": [{"rung": "staged", "ok": False,
                                                "detail": str(e)}]}
        checks.append({"check": "reference passes its hidden tests (airlock)",
                       "ok": bool(last and last["ok"]),
                       "detail": "never checked" if last is None else
                       "; ".join(f"{s['rung']}: {s['detail'][:120]}" for s in last["steps"]
                                 if not s["ok"]) or "green"})
    if mission.get("check_citations"):
        roots = [Path(r) for r in mission["read_roots"]]
        bad = []
        for path, line in CITE.findall(final):
            # only inside the read roots: a cited "../secrets/x.json" must not make
            # the harness open it (Kimi's review, 2026-09-25)
            hit = None
            for r in roots:
                q = (r / path).resolve()
                if q.is_file() and (q == r.resolve() or r.resolve() in q.parents):
                    hit = q
                    break
            if hit is None:
                bad.append(f"{path} (no such file)")
            elif int(line) > len(hit.read_text(encoding="utf-8", errors="replace").splitlines()):
                bad.append(f"{path}:{line} (past end)")
        checks.append({"check": "cited file:line exist", "ok": not bad,
                       "detail": "; ".join(bad[:6]) or f"{len(CITE.findall(final))} citations exist"})
    return checks


def run_mission(mission: dict, chat=None, mcp=None, out_dir: Path = None) -> dict:
    st_schema = _load_crew_module("st_schema")
    st_mission = _load_crew_module("st_mission")
    name = mission["name"]
    out_dir = Path(out_dir or OUT_HOME / name)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = out_dir / "screenshots"
    shots.mkdir(exist_ok=True)
    transcript = open(out_dir / "transcript.jsonl", "w", encoding="utf-8")

    def log(e):
        transcript.write(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"), **e},
                                    ensure_ascii=False) + "\n")
        transcript.flush()

    status_path = out_dir / "status.json"

    def status(state, **kw):
        status_path.write_text(json.dumps({"mission": name, "state": state, "pid": os.getpid(),
                                           "at": dt.datetime.now().isoformat(timespec="seconds"),
                                           **kw}, indent=1), encoding="utf-8")

    server = None
    try:
        return _run(mission, chat, mcp, out_dir, shots, transcript, log, status,
                    st_schema, st_mission, name)
    except BaseException:
        # setup failed before the main try (bad port, MCP server missing): close
        # what was opened and say so (Kimi's review: the handle leaked, status
        # stayed "running")
        if not transcript.closed:
            transcript.close()
        status("failed")
        raise


def _run(mission, chat, mcp, out_dir, shots, transcript, log, status, st_schema,
         st_mission, name):
    server = None
    if mission.get("serve_dir"):
        # Playwright MCP refuses file: URLs; serve ONLY the mission's folder, on loopback.
        server = subprocess.Popen([sys.executable, "-m", "http.server", str(mission["port"]),
                                   "--bind", "127.0.0.1", "--directory", mission["serve_dir"]],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(2)
    own_mcp = mcp is None
    if own_mcp and mission.get("provider") == "local":
        # files, not a browser: read the workspace, stage outputs, run the airlock
        from crew.st_local import LocalProvider
        mcp = LocalProvider(mission["read_roots"], out_dir / "staged",
                            mission["allowed_tools"])
    elif own_mcp:
        # Defence in depth from Qwen's research (job-20260925-074213-913c): the
        # browser may only request the mission's own origins, and no service
        # workers. Playwright MCP says it is "not a security boundary" - the
        # mission guard is; these only narrow what a page can reach.
        from urllib.parse import urlsplit
        origins = sorted({f"{urlsplit(u).scheme}://{urlsplit(u).netloc}"
                          for u in mission.get("url_prefixes", []) if urlsplit(u).netloc})
        # --no-webmcp (0.0.82+, upgraded 2026-09-25): a page may not hand the
        # member tools of its own - a prompt-injection route.
        extra = ["--block-service-workers", "--no-webmcp"] + (
            ["--allowed-origins", ";".join(origins)] if origins else [])
        mcp = McpClient(PLAYWRIGHT + extra + ["--output-dir", str(out_dir / "mcp")],
                        cwd=str(out_dir)).start()
    chat = chat or default_chat(mission.get("member", "Kimi"),
                                int(mission.get("reply_tokens", 8192)))
    guard = st_mission.Mission(mission["allowed_tools"], mission["acting_tools"],
                               mission.get("url_prefixes", []), int(mission["max_steps"]),
                               int(mission["max_actions"]),
                               int(mission.get("max_errors_in_a_row", 3)),
                               int(mission.get("max_repeats", 2)))
    start_balance = _balance()
    cap = float(mission.get("credit_cap_usd", 1.0))
    observed = []                         # every text a tool returned: the evidence
    steps_log, final, stop, turns, tokens = [], None, None, 0, 0
    tools = []
    try:
        offered = [t for t in mcp.tools()
                   if t["name"] in mission["allowed_tools"] and t["name"] not in NEVER]
        tools = [{"type": "function", "function": {
            "name": t["name"], "description": (t.get("description") or "")[:600],
            "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}}
            for t in offered]
        system = (
            f"You are {mission.get('member', 'Kimi')}, on a special-teams mission for a "
            "human+AI crew. You work through the tools provided, and only those"
            + (" - they drive a real browser." if mission.get("provider") != "local" else
               " - they read the workspace, stage your output files (nothing else can be "
               "written) and run the crew's safety and test gates on staged code.")
            + "\n"
            "RULES: do exactly what the mission asks and nothing more - no extra "
            "clicks, pages or changes nobody requested. Every tool call is checked "
            "before it runs; a refusal comes back as the tool result with the reason. "
            "When you are done, answer WITHOUT a tool call: a short report. Put any "
            "text you copied from the page inside `backticks` - each quoted span is "
            "checked against what the tools actually returned, so copy, never "
            "paraphrase. If you did not see something, say so.\n"
            "NOTE: the browser tool's text output replaces some punctuation (dashes, "
            "middle dots) with the character U+FFFD; that is a transport artifact, not "
            "a defect of the page - do not report it.\n"
            f"BUDGET: {mission['max_steps']} tool calls, of which at most "
            f"{mission['max_actions']} clicks/typing. Plan before you act."
            + ("\nYOU MAY READ (use these full paths; relative paths resolve against the "
               "first):\n" + "\n".join(f"- {r}" for r in mission.get("read_roots", []))
               if mission.get("provider") == "local" else ""))
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": mission["goal"]}]
        status("running", steps=0)
        context_chars = int(mission["context_chars"]) if mission.get("context_chars") else (
            350000 if mission.get("provider") == "local" else None)
        max_turns = int(mission.get("max_turns", mission["max_steps"] + 6))
        while True:
            stop = guard.stop_reason()
            if stop:
                break
            bal = _balance()
            if start_balance and bal is not None and start_balance - bal > cap:
                stop = f"credit_cap (${start_balance - bal:.2f} > ${cap:.2f})"
                break
            if turns >= max_turns:
                stop = "max_turns"
                break
            _shrink(messages, context_chars)
            wire = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
            res = chat(wire, tools)
            turns += 1
            if turns == 1:
                # The balance only updates when a call is made: a reading taken
                # before this mission can be hours old and miss regenerations
                # (2026-09-25: 14 h stale, the cap compared against it). The
                # baseline is the reading this first call just refreshed.
                start_balance = _balance() or start_balance
            usage = ((res.get("raw") or {}).get("usage") or {})
            tokens += int(usage.get("total_tokens") or 0)
            msg = ((res.get("raw") or {}).get("choices") or [{}])[0].get("message") or {}
            calls = st_schema.parse_tool_calls(msg)
            log({"event": "reply", "turn": turns, "tokens": usage.get("total_tokens"),
                 "content": (msg.get("content") or "")[:2000],
                 "calls": [{"name": c["name"], "args": c["args"], "error": c["error"]}
                           for c in calls]})
            if not calls:
                final = res.get("content") or msg.get("content") or ""
                stop = "answered"
                break
            # Kimi K3 is trained in "preserved thinking history" mode: the COMPLETE
            # assistant message - reasoning_content included - must go back as-is
            # (Moonshot README, found by Qwen, job-20260925-080012-73e5). Sending
            # only content + tool_calls breaks the documented contract.
            messages.append({k: v for k, v in msg.items()
                             if k in ("role", "content", "tool_calls", "reasoning_content")}
                            | {"role": "assistant", "content": msg.get("content") or ""})
            for c in calls:
                verdict = c["error"] or "; ".join(st_schema.check_call(tools, c["name"], c["args"])) \
                    or guard.check(c["name"], c["args"])
                if verdict:
                    text, ok, kind = f"REFUSED: {verdict}", False, "refused"
                else:
                    kind = "ran"
                    if c["name"] in mission["acting_tools"] and c["args"].get("target"):
                        # visible progress: orange for half a second, photographed
                        shot = str(shots / f"step{guard.steps + 1:02d}-{c['name']}.png")
                        try:
                            h = mcp.call("browser_evaluate", {"element": c["args"].get("element", ""),
                                                              "target": c["args"]["target"],
                                                              "function": ORANGE})
                            time.sleep(0.5)
                            s = mcp.call("browser_take_screenshot", {"filename": shot})
                            log({"event": "highlight", "target": c["args"]["target"],
                                 "highlight_ok": h["ok"], "screenshot_ok": s["ok"],
                                 "detail": (h["text"] if not h["ok"] else s["text"])[:300]})
                        except McpError as e:
                            log({"event": "highlight", "error": str(e)[:300]})
                    try:
                        r = mcp.call(c["name"], c["args"])
                        text, ok = r["text"], r["ok"]
                    except McpError as e:
                        text, ok = f"TOOL ERROR: {e}", False
                    guard.record(c["name"], c["args"], ok)
                    if c["name"] in mission["acting_tools"] and c["args"].get("target"):
                        try:
                            mcp.call("browser_evaluate", {"element": "", "target": c["args"]["target"],
                                                          "function": UNHIGHLIGHT})
                        except McpError:
                            pass
                    observed.append(text)
                text = text[:MAX_RESULT_CHARS]
                left = int(mission["max_steps"]) - guard.steps
                note = f"\n[{left} tool calls left]"
                if left <= 3:
                    note += (" ANSWER NOW: write your final report without a tool call, "
                             "from what you already have.")
                messages.append({"role": "tool", "tool_call_id": c["id"] or c["name"],
                                 "content": text + note})
                steps_log.append({"tool": c["name"], "args": c["args"], "result": kind,
                                  "ok": ok, "detail": text[:160].replace("\n", " ")})
                log({"event": "tool", "tool": c["name"], "args": c["args"], "result": kind,
                     "ok": ok, "chars": len(text), "text": text[:3000]})
            status("running", steps=guard.steps, turns=turns, tokens=tokens)
        if final is None and stop in ("max_steps", "max_turns", "refused_in_a_row"):
            # Out of budget with nothing reported: one last turn, no tools, so the
            # work already done is not thrown away (the crew's LAST REPLY rule).
            messages.append({"role": "user", "content":
                             "Your tool budget is spent. Write your final report NOW, "
                             "without any tool call, from what you have already read. "
                             "Mark anything you could not confirm as (unverified)."})
            wire = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
            try:
                res = chat(wire, tools, "none")
            except TypeError:             # a test double with the two-argument signature
                res = chat(wire, tools)
            turns += 1
            tokens += int(((res.get("raw") or {}).get("usage") or {}).get("total_tokens") or 0)
            msg = ((res.get("raw") or {}).get("choices") or [{}])[0].get("message") or {}
            if not msg.get("tool_calls"):
                final = res.get("content") or msg.get("content") or ""
                stop = f"answered_after_{stop}"
            log({"event": "final_turn", "content": (final or "")[:2000]})
    finally:
        if own_mcp:
            mcp.close()
        if server:
            server.terminate()
        transcript.close()

    # -- grading: what the member claims must be what the tools returned --------------
    # Evidence = what tools returned, plus (file missions) the member's own staged
    # files and the tool names: quoting your own contract's API is not a
    # hallucination (2026-09-26: Kimi's campaign design failed on `render(entries)`).
    extra = [t["function"]["name"] for t in tools] if tools else []
    staged_dir = out_dir / "staged"
    if staged_dir.is_dir():
        extra += [p.read_text(encoding="utf-8", errors="replace")
                  for p in staged_dir.rglob("*") if p.is_file()]
    corpus = re.sub(r"\s+", " ", "\n".join(observed + extra))
    unseen_quotes = [q for q in QUOTE.findall(final or "") if len(q.strip()) >= 12
                     and re.sub(r"\s+", " ", q).strip() not in corpus]
    missing = [e for e in mission.get("expect_observed", []) if e not in corpus]
    checks = [{"check": "answered", "ok": str(stop).startswith("answered"), "detail": stop},
              {"check": "quotes seen", "ok": not unseen_quotes,
               "detail": "; ".join(unseen_quotes[:5]) or "every quote was returned by a tool"},
              {"check": "expected observations", "ok": not missing,
               "detail": "; ".join(missing) or "all seen"}]
    for term in mission.get("must_mention", []):
        checks.append({"check": f"mentions '{term}'",
                       "ok": term.lower() in (final or "").lower(), "detail": ""})
    checks += _local_checks(mission, final or "", out_dir, mcp)
    end_balance = _balance()
    result = {"mission": name, "member": mission.get("member", "Kimi"),
              "passed": all(c["ok"] for c in checks), "stop": stop, "turns": turns,
              "tokens": tokens, "guard": guard.summary(), "checks": checks,
              "credits_start": start_balance, "credits_end": end_balance,
              "screenshots": sorted(p.name for p in shots.glob("*.png"))}
    (out_dir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    rows = "\n".join(f"| {i + 1} | {s['tool']} | `{json.dumps(s['args'])[:80]}` | {s['result']} | "
                     f"{'ok' if s['ok'] else 'no'} |" for i, s in enumerate(steps_log))
    report = f"""# Special-teams mission: {name}

Member: {result['member']} - native tool calling; tools: {"workspace files (read, stage, check)" if mission.get("provider") == "local" else "Playwright MCP (headless, isolated)"}.
Outcome: **{'PASSED' if result['passed'] else 'NOT PASSED'}** - stop: {stop}; {turns} turns;
{tokens:,} tokens; guard {json.dumps(result['guard'])}.
Credits (provider reading): start {start_balance}, end {end_balance}.

## Mission
{mission['goal']}

## Final answer (the member's words)
{final or '(none)'}

## Checks
""" + "\n".join(f"- [{'x' if c['ok'] else ' '}] {c['check']}: {c['detail']}" for c in checks) + f"""

## Steps
| # | tool | args | result | ok |
|---|---|---|---|---|
{rows}

Screenshots of each highlighted action: `{shots}`
Transcript: `{out_dir / 'transcript.jsonl'}`
"""
    (out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    status("finished", passed=result["passed"], stop=stop)
    return result


if __name__ == "__main__":
    m = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    r = run_mission(m)
    print(json.dumps({k: r[k] for k in ("mission", "passed", "stop", "turns", "tokens")}))
    sys.exit(0 if r["passed"] else 1)
