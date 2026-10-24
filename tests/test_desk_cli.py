"""desk_cli.py: the Review Desk as The Crew's control room calls it.

The control room never writes queue.ini; these check that the bridge keeps the Desk's
rules (approve needs no words, the others need a reason; read items close when seen;
a cleared decision keeps its note as a draft; SEND hands over only what is ready).
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew.reviewdesk import review_index  # noqa: E402
from crew.runners import desk_cli, review_desk  # noqa: E402


class DeskCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._home = review_desk.home
        review_desk.home = lambda: self.tmp / "review"
        self.addCleanup(setattr, review_desk, "home", self._home)
        self.file = self.tmp / "work.md"
        self.file.write_text("# work\n", encoding="utf-8")
        review_desk.save_queue([
            review_index.new_item(item_id="pa:work", title="Check the contract wording",
                                  path=str(self.file), origin="PA:Claude"),
            review_index.new_item(item_id="pa:fyi", title="READ - what's new",
                                  path=str(self.file), origin="PA:Claude"),
        ])

    def run_cli(self, *args, note=""):
        out = io.BytesIO()
        stdin, stdout = sys.stdin, sys.stdout
        sys.stdin = SimpleNamespace(buffer=io.BytesIO(note.encode("utf-8")))
        sys.stdout = SimpleNamespace(buffer=out)       # desk_cli speaks bytes only
        try:
            code = desk_cli.main(list(args))
        finally:
            sys.stdin, sys.stdout = stdin, stdout
        return code, json.loads(out.getvalue().decode("utf-8"))

    def item(self, item_id):
        return next(i for i in review_desk.load_queue() if i["item_id"] == item_id)

    def test_list_reports_kinds_and_counts(self):
        code, got = self.run_cli("list")
        self.assertEqual(code, 0)
        kinds = {i["item_id"]: i["kind"] for i in got["items"]}
        self.assertEqual(kinds, {"pa:work": "decide", "pa:fyi": "read"})
        self.assertEqual(got["summary"]["pending"], 2)
        self.assertEqual(got["ready"], 0)
        self.assertEqual(got["min_note_chars"], 12)

    def test_approve_needs_no_note(self):
        code, got = self.run_cli("decide", "pa:work", "approve")
        self.assertEqual((code, got["ok"]), (0, True))
        self.assertEqual(self.item("pa:work")["decision"], "approve")
        self.assertEqual(self.item("pa:work")["state"], "decided")
        self.assertEqual(got["ready"], 1)

    def test_reject_without_a_reason_is_refused_and_nothing_is_written(self):
        code, got = self.run_cli("decide", "pa:work", "reject", note="no")
        self.assertEqual((code, got["ok"]), (1, False))
        self.assertIn("reason of at least 12 characters", got["problem"])
        self.assertEqual(self.item("pa:work")["decision"], "")

    def test_reject_with_a_reason_keeps_the_note_and_drops_the_draft(self):
        self.run_cli("draft", "pa:work", note="half a thought")
        code, got = self.run_cli("decide", "pa:work", "reject",
                                 note="Rule 3 contradicts étape 4 - fix the order")
        self.assertEqual(code, 0)
        self.assertEqual(self.item("pa:work")["note"], "Rule 3 contradicts étape 4 - fix the order")
        self.assertNotIn("pa:work", review_desk.load_drafts())

    def test_seen_closes_a_read_item(self):
        self.run_cli("decide", "pa:fyi", "approve")
        self.assertEqual(self.item("pa:fyi")["state"], "closed")
        self.assertEqual(review_desk.ready_to_send(review_desk.load_queue()), [])

    def test_unknown_decision_and_unknown_item(self):
        self.assertIn("is not one of", self.run_cli("decide", "pa:work", "maybe",
                                                    note="a long enough note")[1]["problem"])
        self.assertIn("not in the queue", self.run_cli("decide", "nope", "approve")[1]["problem"])

    def test_undecide_keeps_the_note_as_a_draft(self):
        self.run_cli("decide", "pa:work", "question", note="Which profile does this use?")
        code, got = self.run_cli("undecide", "pa:work")
        self.assertEqual(code, 0)
        self.assertEqual(self.item("pa:work")["decision"], "")
        self.assertEqual(self.item("pa:work")["state"], "pending")
        self.assertEqual(review_desk.load_drafts()["pa:work"]["note"], "Which profile does this use?")

    def test_draft_blank_removes_it(self):
        self.run_cli("draft", "pa:work", note="keep me")
        self.assertIn("pa:work", review_desk.load_drafts())
        self.run_cli("draft", "pa:work", note="   ")
        self.assertNotIn("pa:work", review_desk.load_drafts())

    def test_send_hands_over_only_ready_items(self):
        code, got = self.run_cli("send")
        self.assertEqual((code, got["ok"]), (1, False))
        self.run_cli("decide", "pa:work", "approve")
        code, got = self.run_cli("send")
        self.assertEqual((code, got["count"]), (0, 1))
        self.assertEqual(self.item("pa:work")["state"], "closed")
        handoff = json.loads((self.tmp / "review" / "handoff.json").read_text(encoding="utf-8"))
        self.assertEqual([i["item_id"] for i in handoff["items"]], ["pa:work"])

    def test_a_changed_file_is_flagged(self):
        self.run_cli("decide", "pa:work", "approve")
        self.assertFalse(self.run_cli("list")[1]["items"][0]["changed"])
        self.file.write_text("# work, edited\n", encoding="utf-8")
        self.assertTrue(self.run_cli("list")[1]["items"][0]["changed"])


if __name__ == "__main__":
    unittest.main()
