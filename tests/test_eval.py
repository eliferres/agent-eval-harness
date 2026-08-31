"""End-to-end tests for the eval.py CLI.

These run the shipped demo through every subcommand in a temp runs
directory, so a green suite means the README walkthrough works.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import harness  # noqa: E402

TASK = "demo/tasks/word-wrap"
ARM_A = "demo/arms/word-wrap/arm-a"
ARM_B = "demo/arms/word-wrap/arm-b"


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name) / "runs"
        self.addCleanup(self.tmp.cleanup)

    def eval_py(self, *args):
        return subprocess.run(
            [sys.executable, "eval.py", "--runs", str(self.runs), *args],
            cwd=str(REPO), capture_output=True, text=True,
        )

    def test_demo_flow_end_to_end(self):
        for arm in (ARM_A, ARM_B):
            self.assertEqual(self.eval_py("check", TASK, arm).returncode, 0, arm)
        self.assertEqual(self.eval_py("grade", TASK, ARM_A).returncode, 0)

        # The whole point of the demo: arm-b passes everything it can see
        # and fails an edge case it was never shown.
        graded_b = self.eval_py("grade", TASK, ARM_B)
        self.assertEqual(graded_b.returncode, 1)
        self.assertIn("hidden tests FAIL", graded_b.stdout)

        self.assertEqual(self.eval_py("pack", TASK, ARM_A, ARM_B).returncode, 0)
        recorded = self.eval_py("record", TASK, "demo/scorecard-filled.md")
        self.assertEqual(recorded.returncode, 0, recorded.stdout)
        self.assertIn("unblinds to arm-a", recorded.stdout)

        shipped = self.eval_py("ship", TASK, ARM_A)
        self.assertEqual(shipped.returncode, 0, shipped.stdout)
        self.assertIn("SHIP", shipped.stdout)
        self.assertNotIn("RED", shipped.stdout)

        refused = self.eval_py("ship", TASK, ARM_B)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("NO SHIP", refused.stdout)

    def test_grade_refuses_an_arm_holding_the_hidden_tests(self):
        contaminated = Path(self.tmp.name) / "arm-c"
        contaminated.mkdir()
        harness.stage(REPO / ARM_A, contaminated)
        harness.stage(REPO / TASK / harness.HIDDEN, contaminated)

        proc = self.eval_py("grade", TASK, str(contaminated))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("REFUSED", proc.stdout)
        ledger = json.loads(harness.ledger_path(self.runs, "word-wrap").read_text())
        self.assertFalse(ledger["arms"]["arm-c"]["blindness"]["clean"])
        self.assertNotIn("hidden", ledger["arms"]["arm-c"])

    def test_init_scaffolds_a_fixture_the_harness_accepts(self):
        scaffold = Path(self.tmp.name) / "new-task"
        proc = self.eval_py("init", str(scaffold))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        task = harness.load_task(scaffold)
        self.assertEqual(task["name"], "new-task")
        self.assertEqual(len(task["seed"]), 16)
        self.assertEqual(self.eval_py("init", str(scaffold)).returncode, 2)

    def test_ship_refuses_before_anything_is_recorded(self):
        proc = self.eval_py("ship", TASK, ARM_A)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("never run", proc.stdout)
        self.assertIn("no scorecard filed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
