"""pa_engine.py and the pa_session.py parts it shares: the chat engine's OpenCode config."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "crew" / "runners"))

import pa_engine  # noqa: E402
import pa_session  # noqa: E402

STAFF = {
    "members": {"Kimi": {"context_window": 262144}, "Gordon": {}},
    "pa": {
        "approved": ["Claude", "Kimi", "Qwen", "Gordon"],
        "scopes": {
            "Claude": {"runtime": "claude-code"},
            "Kimi": {"runtime": "opencode", "model": "moonshot/Kimi-K3", "steps": 40,
                     "reply_tokens": 24576},
            "Qwen": {"runtime": "opencode", "model": "qwen/Qwen3.8-27B", "reply_tokens": 65536},
            "Gordon": {"runtime": "opencode", "model": "deepseek/DeepSeek-V4.1-Flash",
                       "steps": 60},
        },
    },
}
BRIEFS = {pa: Path(f"C:/state/pa/{pa}/brief.md") for pa in ("Kimi", "Qwen", "Gordon")}


class EngineConfigTests(unittest.TestCase):
    def test_engine_pas_are_the_approved_opencode_ones_in_order(self):
        self.assertEqual(pa_engine.engine_pas(STAFF), ["Kimi", "Qwen", "Gordon"])
        self.assertEqual(pa_engine.engine_pas({}), [])

    def test_a_plan_and_an_assign_agent_per_pa(self):
        cfg = pa_engine.engine_config(STAFF, BRIEFS)
        self.assertEqual(sorted(cfg["agent"]), ["Gordon-assign", "Gordon-plan", "Kimi-assign",
                                                "Kimi-plan", "Qwen-assign", "Qwen-plan"])
        for mode in ("plan", "assign"):
            kimi = cfg["agent"][f"Kimi-{mode}"]
            self.assertEqual(kimi["model"], "synthetic/moonshot/Kimi-K3")
            self.assertEqual(kimi["prompt"], "{file:C:/state/pa/Kimi/brief.md}")
            self.assertEqual(kimi["steps"], 40)
        self.assertNotIn("steps", cfg["agent"]["Qwen-plan"])
        self.assertEqual(cfg["default_agent"], "Kimi-plan")

    def test_plan_mode_cannot_assign_or_edit_beyond_its_artifacts(self):
        chats = Path("C:/state/pa/chats")
        plan = pa_engine.engine_config(STAFF, BRIEFS, chats)["agent"]["Gordon-plan"]["permission"]
        self.assertEqual((plan["crew_crew_submit"], plan["crew_crew_review"]), ("deny", "deny"))
        self.assertEqual(list(plan["edit"])[0], "*")
        self.assertEqual(plan["edit"]["*"], "deny")
        self.assertIn("allow", plan["edit"].values())

    def test_assign_mode_may_assign_and_asks_before_edits(self):
        chats = Path("C:/state/pa/chats")
        assign = pa_engine.engine_config(STAFF, BRIEFS, chats)["agent"]["Gordon-assign"]["permission"]
        self.assertNotIn("crew_crew_submit", assign)
        self.assertEqual(assign["edit"]["*"], "ask")
        self.assertEqual(sorted(set(assign["edit"].values())), ["allow", "ask"])

    def test_models_carry_each_pas_limits(self):
        models = pa_engine.engine_config(STAFF, BRIEFS)["provider"]["synthetic"]["models"]
        self.assertEqual(models["moonshot/Kimi-K3"]["limit"], {"output": 24576, "context": 262144})
        self.assertEqual(models["deepseek/DeepSeek-V4.1-Flash"]["limit"],
                         {"output": 32768, "context": 200000})

    def test_edits_and_commands_ask_the_human(self):
        for name, agent in pa_engine.engine_config(STAFF, BRIEFS)["agent"].items():
            permission = agent["permission"]
            other = "deny" if name.endswith("-plan") else "ask"
            self.assertEqual((permission["edit"], permission["bash"]["*"], permission["webfetch"]),
                             ("ask", other, "ask"))
            self.assertNotIn("Remove-Item*", permission["bash"])

    def test_plan_mode_refuses_writing_commands_and_redirections(self):
        # 2026-10-25: a plan-mode PA got a shell card allowed and rewrote another chat's files.
        agents = pa_engine.engine_config(STAFF, BRIEFS)["agent"]
        plan, assign = agents["Kimi-plan"]["permission"]["bash"], agents["Kimi-assign"]["permission"]["bash"]
        self.assertEqual((plan["*"], plan["*>*"]), ("deny", "deny"))
        self.assertEqual((assign["*"], assign["*>*"]), ("ask", "ask"))
        self.assertEqual(list(plan)[-1], "*>*", "the redirection rule must come last: the last match wins")
        self.assertEqual(plan["Get-ChildItem*"], "allow")

    def test_crew_mcp_is_shared_with_the_worker_off(self):
        crew = pa_engine.engine_config(STAFF, BRIEFS)["mcp"]["crew"]
        self.assertEqual(crew["environment"], {"CREW_CLIENT": "TheCrew-chat", "CREW_WORKER": "0"})
        self.assertTrue(crew["command"][-1].endswith("crew_server.py"))

    def test_the_key_is_never_in_the_config(self):
        with mock.patch.dict(os.environ, {"SYNTHETIC_API_KEY": "sk-not-a-real-key"}):
            text = json.dumps(pa_engine.engine_config(STAFF, BRIEFS))
        self.assertNotIn("sk-not-a-real-key", text)
        self.assertIn("{env:SYNTHETIC_API_KEY}", text)

    def test_read_only_commands_run_without_a_card_and_the_rest_ask(self):
        bash = pa_engine.engine_config(STAFF, BRIEFS)["agent"]["Kimi-assign"]["permission"]["bash"]
        self.assertEqual(list(bash)[0], "*")
        self.assertEqual(bash["*"], "ask")
        self.assertEqual(bash["python crew/runners/active_status.py*"], "allow")
        self.assertEqual(bash["python crew\\runners\\active_status.py*"], "allow")
        self.assertEqual(bash["git log*"], "allow")
        self.assertNotIn("python crew/runners/night_shift.py*", bash, "it writes a report")

    def test_the_pas_shell_finds_the_real_python_first(self):
        env = pa_session.with_real_python({"PATH": r"C:\hermes\venv\Scripts"})
        first = env["PATH"].split(os.pathsep)[0]
        self.assertEqual(first, str(Path(sys.executable).parent))
        self.assertTrue(env["PATH"].endswith(r"C:\hermes\venv\Scripts"))

    def test_single_pa_config_is_unchanged(self):
        cfg = pa_session.opencode_config("Gordon", STAFF["pa"]["scopes"]["Gordon"], STAFF,
                                         BRIEFS["Gordon"], worker=True)
        self.assertEqual(list(cfg["agent"]), ["pa"])
        self.assertEqual(cfg["default_agent"], "pa")
        self.assertEqual(cfg["agent"]["pa"]["description"], "Gordon is the PA of The Crew")
        self.assertEqual(cfg["agent"]["pa"]["permission"]["edit"], "ask")
        self.assertNotIn("crew_crew_submit", cfg["agent"]["pa"]["permission"])
        self.assertEqual(cfg["mcp"]["crew"]["environment"],
                         {"CREW_CLIENT": "OpenCode-Gordon", "CREW_WORKER": "1"})
        self.assertEqual((cfg["autoupdate"], cfg["share"]), (False, "disabled"))


if __name__ == "__main__":
    unittest.main()
