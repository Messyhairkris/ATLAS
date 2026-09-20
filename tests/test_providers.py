"""Unit tests for the API harness provider layer (v3-service/providers/).

Run: PYTHONPATH=v3-service python -m pytest tests/test_providers.py -q
(or python tests/test_providers.py)
"""

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "v3-service"))


FAKE_CONFIG = {
    "providers": {
        "synthetic": {
            "type": "openai-compat",
            "base_url": "https://example.invalid",
            "auth": {"type": "bearer", "api_key_env": "FAKE_SYN_KEY"},
            "capabilities": {
                "supports_streaming": True,
                "accepts_seed": True,
                "accepts_chat_template_kwargs": False,
                "accepts_logprobs": False,
            },
            "chat_models": ["hf:zai-org/GLM-4.7-Flash", "hf:openai/gpt-oss-120b"],
            "embeddings": {"path": "/v1/embeddings",
                           "model": "hf:nomic-ai/nomic-embed-text-v1.5",
                           "billed": False},
        }
    }
}


class ProviderTestCase(unittest.TestCase):
    def setUp(self):
        self._env_backup = dict(os.environ)
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(FAKE_CONFIG, tmp)
        tmp.close()
        self.config_path = tmp.name
        os.environ["ATLAS_PROVIDERS_FILE"] = self.config_path
        os.environ.pop("ATLAS_PROVIDER", None)
        os.environ.pop("ATLAS_CHAT_MODEL", None)
        os.environ["FAKE_SYN_KEY"] = "test-key-123"
        # Re-import fresh against the temp config
        global registry, telemetry
        for mod in list(sys.modules):
            if mod.startswith("providers"):
                del sys.modules[mod]
        import providers.registry as registry_mod
        import providers.telemetry as telemetry_mod
        registry = importlib.reload(registry_mod)
        telemetry = importlib.reload(telemetry_mod)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)
        os.unlink(self.config_path)

    def test_no_provider_opt_in_returns_none(self):
        self.assertIsNone(registry.chat_target())

    def test_chat_target_resolution(self):
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        target = registry.chat_target()
        self.assertEqual(target["url"],
                         "https://example.invalid/v1/chat/completions")
        self.assertEqual(target["model"], "hf:zai-org/GLM-4.7-Flash")
        self.assertEqual(target["headers"]["Authorization"],
                         "Bearer test-key-123")

    def test_model_override(self):
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        os.environ["ATLAS_CHAT_MODEL"] = "hf:openai/gpt-oss-120b"
        self.assertEqual(registry.chat_target()["model"],
                         "hf:openai/gpt-oss-120b")

    def test_embedding_target(self):
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        emb = registry.embedding_target()
        self.assertEqual(emb["url"], "https://example.invalid/v1/embeddings")
        self.assertEqual(emb["model"], "hf:nomic-ai/nomic-embed-text-v1.5")
        self.assertFalse(emb["billed"])

    def test_unknown_provider_raises(self):
        os.environ["ATLAS_PROVIDER"] = "nope"
        with self.assertRaises(registry.ProviderError):
            registry.chat_target()

    def test_filter_chat_body_strips_unsupported_fields(self):
        caps = {"accepts_chat_template_kwargs": False,
                "accepts_logprobs": False, "accepts_seed": True,
                "accepts_stream_options": False}
        body = {"messages": [], "seed": 7, "logprobs": True,
                "top_logprobs": 1,
                "chat_template_kwargs": {"enable_thinking": False},
                "stream": True, "stream_options": {"include_usage": True}}
        out = registry.filter_chat_body(body, caps)
        self.assertNotIn("chat_template_kwargs", out)
        self.assertNotIn("logprobs", out)
        self.assertNotIn("top_logprobs", out)
        self.assertEqual(out["seed"], 7)
        self.assertTrue(out["stream"])
        self.assertNotIn("stream_options", out)

        out2 = registry.filter_chat_body(body, {**caps, "supports_streaming": False})
        self.assertFalse(out2["stream"])

    def test_deny_list_blocks_model_by_id_or_nickname(self):
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        os.environ["ATLAS_CHAT_MODEL"] = "hf:openai/gpt-oss-120b"
        os.environ["ATLAS_DENY_MODELS"] = "hf:openai/gpt-oss-120b"
        with self.assertRaises(registry.ProviderError):
            registry.chat_target()
        os.environ["ATLAS_DENY_MODELS"] = "hf:moonshotai/Kimi-K3"
        self.assertEqual(registry.chat_target()["model"],
                         "hf:openai/gpt-oss-120b")

    def test_reasoning_effort_stripped_unless_declared(self):
        body = {"messages": [], "reasoning_effort": "high"}
        self.assertNotIn("reasoning_effort",
                         registry.filter_chat_body(body, {}))
        self.assertEqual(registry.filter_chat_body(
            body, {"accepts_reasoning_effort": True})["reasoning_effort"],
            "high")

    def test_unpriced_model_costs_none_not_zero(self):
        self.assertIsNone(telemetry.cost_usd(None, 1000, 1000))
        self.assertIsNone(telemetry.cost_usd(
            {"in_per_mtok": None, "out_per_mtok": 1.0}, 1000, 1000))
        self.assertAlmostEqual(telemetry.cost_usd(
            {"in_per_mtok": 1.0, "out_per_mtok": 2.0}, 1_000_000, 500_000),
            2.0)

    def test_telemetry_context_tags_and_nests(self):
        log = Path(tempfile.mkdtemp()) / "t.jsonl"
        os.environ["ATLAS_TELEMETRY_FILE"] = str(log)
        with telemetry.context(run_id="r1", role="junior"):
            with telemetry.context(task_id="p1", attempt=0):
                telemetry.record({"model": "m"})
            with telemetry.context(role="senior"):
                telemetry.record({"model": "k"})
        telemetry.record({"model": "bare"})
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        self.assertEqual((rows[0]["run_id"], rows[0]["task_id"],
                          rows[0]["role"]), ("r1", "p1", "junior"))
        self.assertEqual(rows[1]["role"], "senior")
        self.assertNotIn("task_id", rows[1])
        self.assertNotIn("run_id", rows[2])

    def test_key_fallback_config_file(self):
        keyfile = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"providers": {"synthetic": {"api_key": "fallback-key-9"}}},
                  keyfile)
        keyfile.close()
        os.environ.pop("FAKE_SYN_KEY")
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        cfg = json.loads(json.dumps(FAKE_CONFIG))
        cfg["providers"]["synthetic"]["auth"]["api_key_fallback"] = {
            "config": keyfile.name,
            "key_selector": "providers.synthetic.api_key",
        }
        with open(self.config_path, "w") as fh:
            json.dump(cfg, fh)
        os.environ.pop("ATLAS_PROVIDER", None)
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        target = registry.chat_target()
        self.assertEqual(target["headers"]["Authorization"],
                         "Bearer fallback-key-9")
        os.unlink(keyfile.name)

    def test_telemetry_appends_jsonl(self):
        tmpdir = tempfile.mkdtemp()
        os.environ["ATLAS_TELEMETRY_FILE"] = str(Path(tmpdir) / "t.jsonl")
        telemetry.record({"provider": "synthetic", "total_tokens": 42})
        lines = (Path(tmpdir) / "t.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertEqual(event["total_tokens"], 42)
        self.assertIn("ts", event)

    def test_summarize_usage(self):
        data = {"usage": {"prompt_tokens": 10, "completion_tokens": 20,
                          "total_tokens": 30}}
        self.assertEqual(telemetry.summarize_usage(data),
                         {"prompt_tokens": 10, "completion_tokens": 20,
                          "total_tokens": 30})


class ExtractFilesTestCase(unittest.TestCase):
    def _load_battery(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "godot_battery", REPO_ROOT / "experiments" / "godot_battery.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_extract_files_contract(self):
        mod = self._load_battery()
        text = ("```project.godot\nconfig_version=5\n```\n"
                "prose to ignore\n```scenes/main.tscn\n[gd_scene format=3]\n```\n")
        files = mod.extract_files(text)
        self.assertIn("project.godot", files)
        self.assertIn("scenes/main.tscn", files)
        self.assertNotIn("prose to ignore", files)

    def test_language_tags_rejected_as_filenames(self):
        """Regression: run 20260917-232709 — GLM fenced ```gdscript/```xml and
        those were extracted as files named 'gdscript', causing vacuous passes."""
        mod = self._load_battery()
        text = "```gdscript\nextends CharacterBody2D\n```\n```xml\n[gd_scene]\n```\n"
        files = mod.extract_files(text)
        self.assertEqual(files, {})

    def test_language_tag_with_path_header_recovered(self):
        """Observed 20260918 run: all models fence as ```gdscript with the path
        as a first-line comment. Contract widening: recover the filename."""
        mod = self._load_battery()
        text = ("```gdscript\n# scripts/player.gd\nextends CharacterBody2D\n```\n"
                "```gdscript\n# levels/level_1.tscn yada\n[gd_scene format=3]\n```\n"
                "```gdscript\n# just a comment, no path\nextends Node\n```\n")
        files = mod.extract_files(text)
        self.assertIn("scripts/player.gd", files)
        self.assertIn("levels/level_1.tscn", files)
        self.assertEqual(len(files), 2)

    def test_extensionless_and_escape_paths_rejected(self):
        mod = self._load_battery()
        text = "```README\nno ext\n```\n```../evil.gd\nextends Node\n```\n"
        files = mod.extract_files(text)
        self.assertEqual(files, {})

    def test_expected_coverage(self):
        mod = self._load_battery()
        cov = mod.expected_coverage(1, {"project.godot": "x",
                                        "scenes/main.tscn": "y",
                                        "scripts/main.gd": "z"})
        self.assertTrue(all(cov.values()))
        cov2 = mod.expected_coverage(1, {"gdscript": "x"})
        self.assertFalse(all(cov2.values()))


if __name__ == "__main__":
    unittest.main()
