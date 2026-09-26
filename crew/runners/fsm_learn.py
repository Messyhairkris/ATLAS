"""Learn a UI's state machine before any LLM sees it (experimental).

Kris, 2026-09-26: "If this tool can help map every option out before an LLM even
sees it, things like testing our products or reverse engineering efforts become
easier." Based on Huang & Peleska, "Testing and Learning Symbolic Finite State
Machines" (arXiv 2609.25603): learn the system as a (Mealy) state machine by
active automata learning (L*), answer equivalence queries with the W-method,
which is COMPLETE for any system with at most `max_states` states.

No model calls: the harness probes the page through Playwright MCP (headless,
isolated), resetting before every query. The output is the learned machine
(Graphviz .dot), the query count, and the W-method test suite - which can become
hidden tests or regression tests, and a map a crew member reads before working.

  python C:/Users/user/ATLAS-api-harness/crew/runners/fsm_learn.py SPEC.json

SPEC: {"name", "serve_dir", "port", "page", "setup_js" (returns the input
alphabet as {name: [selector...]}), "observe_js", "max_states"}
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from aalpy.base import SUL  # noqa: E402
from aalpy.learning_algs import run_Lstar  # noqa: E402
from aalpy.oracles import WMethodEqOracle  # noqa: E402

from crew.mcp_client import McpClient  # noqa: E402

PLAYWRIGHT = ["node", "C:/Users/user/playwright-mcp-setup/node_modules/@playwright/mcp/cli.js",
              "--headless", "--isolated", "--browser", "chromium", "--block-service-workers",
              "--no-webmcp"]


def _result(text: str):
    """The JSON value from a browser_evaluate result."""
    m = re.search(r"### Result\s*\n(.*?)(?:\n###|\Z)", text, re.DOTALL)
    raw = (m.group(1) if m else text).strip().strip("`").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class PageSUL(SUL):
    """A web page as a system under learning. Inputs are CSS selectors to click;
    the output after each input is whatever observe_js returns."""

    def __init__(self, mcp: McpClient, url: str, inputs: dict, observe_js: str):
        super().__init__()
        self.mcp, self.url, self.inputs, self.observe_js = mcp, url, inputs, observe_js
        self.steps = self.resets = 0

    def pre(self):
        # reset: forget saved answers, then load the page fresh. The page SAVES again
        # on beforeunload, which undid a plain clear() - the learner caught it as
        # non-determinism (2026-09-26). A listener added now runs after the page's
        # own save, so storage is empty when the next load reads it.
        self.mcp.call("browser_evaluate", {"function":
                      "() => { localStorage.clear(); window.addEventListener("
                      "'beforeunload', () => localStorage.clear()); return true; }"})
        self.mcp.call("browser_navigate", {"url": self.url})
        self.resets += 1

    def post(self):
        pass

    def step(self, letter):
        self.steps += 1
        js = ("() => { const b = document.querySelector(%s); if (!b) return 'MISSING'; "
              "b.click(); return (%s)(); }" % (json.dumps(self.inputs[letter]), self.observe_js))
        r = self.mcp.call("browser_evaluate", {"function": js})
        return str(_result(r["text"])) if r["ok"] else "ERROR"


def learn(spec: dict) -> dict:
    out = REPO / "runs" / "crew" / "fsm" / spec["name"]
    out.mkdir(parents=True, exist_ok=True)
    status = out / "status.json"
    status.write_text(json.dumps({"state": "running", "started": time.strftime("%H:%M:%S")}))
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(spec["port"]), "--bind",
                               "127.0.0.1", "--directory", spec["serve_dir"]],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(2)
    url = f"http://127.0.0.1:{spec['port']}/{spec['page']}"
    mcp = McpClient(PLAYWRIGHT + ["--allowed-origins", f"http://127.0.0.1:{spec['port']}",
                                  "--output-dir", str(out / "mcp")], cwd=str(out)).start()
    t0 = time.time()
    try:
        mcp.call("browser_navigate", {"url": url})
        inputs = _result(mcp.call("browser_evaluate", {"function": spec["setup_js"]})["text"])
        if not isinstance(inputs, dict) or not inputs:
            raise SystemExit(f"setup_js did not return an input alphabet: {inputs!r}")
        sul = PageSUL(mcp, url, inputs, spec["observe_js"])
        alphabet = list(inputs)
        oracle = WMethodEqOracle(alphabet, sul, max_number_of_states=int(spec["max_states"]))
        model = run_Lstar(alphabet, sul, oracle, automaton_type="mealy", print_level=0)
    finally:
        mcp.close()
        server.terminate()
    dot = str(model)
    (out / "model.dot").write_text(dot, encoding="utf-8")
    result = {"name": spec["name"], "states": len(model.states), "alphabet": alphabet,
              "inputs": inputs, "max_states": spec["max_states"],
              "resets": sul.resets, "steps": sul.steps,
              "seconds": round(time.time() - t0, 1)}
    (out / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    status.write_text(json.dumps({"state": "finished", **result}))
    return result


if __name__ == "__main__":
    r = learn(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    print(json.dumps(r, indent=1))
