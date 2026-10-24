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

    def test_one_agent_per_pa_with_its_model_and_brief(self):
        cfg = pa_engine.engine_config(STAFF, BRIEFS)
        self.assertEqual(sorted(cfg["agent"]), ["Gordon", "Kimi", "Qwen"])
        kimi = cfg["agent"]["Kimi"]
        self.assertEqual(kimi["model"], "synthetic/moonshot/Kimi-K3")
        self.assertEqual(kimi["prompt"], "{file:C:/state/pa/Kimi/brief.md}")
        self.assertEqual(kimi["steps"], 40)
        self.assertNotIn("steps", cfg["agent"]["Qwen"])
        self.assertEqual(cfg["default_agent"], "Kimi")

    def test_models_carry_each_pas_limits(self):
        models = pa_engine.engine_config(STAFF, BRIEFS)["provider"]["synthetic"]["models"]
        self.assertEqual(models["moonshot/Kimi-K3"]["limit"], {"output": 24576, "context": 262144})
        self.assertEqual(models["deepseek/DeepSeek-V4.1-Flash"]["limit"],
                         {"output": 32768, "context": 200000})

    def test_edits_and_commands_ask_the_human(self):
        for agent in pa_engine.engine_config(STAFF, BRIEFS)["agent"].values():
            self.assertEqual({k: agent["permission"][k] for k in ("edit", "bash", "webfetch")},
                             {"edit": "ask", "bash": "ask", "webfetch": "ask"})

    def test_crew_mcp_is_shared_with_the_worker_off(self):
        crew = pa_engine.engine_config(STAFF, BRIEFS)["mcp"]["crew"]
        self.assertEqual(crew["environment"], {"CREW_CLIENT": "TheCrew-chat", "CREW_WORKER": "0"})
        self.assertTrue(crew["command"][-1].endswith("crew_server.py"))

    def test_the_key_is_never_in_the_config(self):
        with mock.patch.dict(os.environ, {"SYNTHETIC_API_KEY": "sk-not-a-real-key"}):
            text = json.dumps(pa_engine.engine_config(STAFF, BRIEFS))
        self.assertNotIn("sk-not-a-real-key", text)
        self.assertIn("{env:SYNTHETIC_API_KEY}", text)

    def test_single_pa_config_is_unchanged(self):
        cfg = pa_session.opencode_config("Gordon", STAFF["pa"]["scopes"]["Gordon"], STAFF,
                                         BRIEFS["Gordon"], worker=True)
        self.assertEqual(list(cfg["agent"]), ["pa"])
        self.assertEqual(cfg["default_agent"], "pa")
        self.assertEqual(cfg["agent"]["pa"]["description"], "Gordon as the PA of The Crew")
        self.assertEqual(cfg["mcp"]["crew"]["environment"],
                         {"CREW_CLIENT": "OpenCode-Gordon", "CREW_WORKER": "1"})
        self.assertEqual((cfg["autoupdate"], cfg["share"]), (False, "disabled"))


if __name__ == "__main__":
    unittest.main()
