"""End-to-end tests for the agent_eval.py CLI.

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

import eval_harness as harness  # noqa: E402

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
            [sys.executable, "agent_eval.py", "--runs", str(self.runs), *args],
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

    def green_run(self, arm_dir):
        """Take one arm all the way to four green legs. Returns the ship result."""
        for args in (("check", TASK, arm_dir), ("grade", TASK, arm_dir),
                     ("pack", TASK, arm_dir, ARM_B)):
            proc = self.eval_py(*args)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.eval_py("record", TASK, "demo/scorecard-filled.md").returncode, 0)
        return self.eval_py("ship", TASK, arm_dir)

    def test_an_untouched_arm_still_ships(self):
        arm = Path(self.tmp.name) / "arm-a"
        harness.stage(REPO / ARM_A, arm, skip_meta=False)
        shipped = self.green_run(str(arm))
        self.assertEqual(shipped.returncode, 0, shipped.stdout)
        self.assertIn("SHIP", shipped.stdout)

    def test_ship_refuses_an_arm_edited_after_its_legs_passed(self):
        # The result in the ledger is only worth anything if it describes the
        # code that is there now. Pass every leg, then swap the solution.
        arm = Path(self.tmp.name) / "arm-a"
        harness.stage(REPO / ARM_A, arm, skip_meta=False)
        self.assertEqual(self.green_run(str(arm)).returncode, 0)

        (arm / "solution.py").write_text("def wrap(text, width):\n    return []\n",
                                         encoding="utf-8")
        refused = self.eval_py("ship", TASK, str(arm))
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("REFUSED", refused.stdout)
        self.assertIn("arm-a changed after the visible tests leg tested it", refused.stdout)
        self.assertNotIn("SHIP\n", refused.stdout)

    def test_ship_refuses_an_arm_copied_somewhere_else_and_edited(self):
        # Arms are keyed by folder name. A copy under a different parent
        # keeps the name, so without a path check the untouched original
        # would clear the edited copy.
        arm = Path(self.tmp.name) / "arm-a"
        harness.stage(REPO / ARM_A, arm, skip_meta=False)
        self.assertEqual(self.green_run(str(arm)).returncode, 0)

        copy = Path(self.tmp.name) / "elsewhere" / "arm-a"
        harness.stage(arm, copy, skip_meta=False)
        with (copy / "solution.py").open("a", encoding="utf-8") as handle:
            handle.write("\nSMUGGLED = True\n")

        refused = self.eval_py("ship", TASK, str(copy))
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("REFUSED", refused.stdout)
        self.assertIn(str(copy.resolve()), refused.stdout)
        self.assertNotIn("SHIP\n", refused.stdout)

    def test_ship_refuses_a_result_recorded_without_a_fingerprint(self):
        arm = Path(self.tmp.name) / "arm-a"
        harness.stage(REPO / ARM_A, arm, skip_meta=False)
        self.assertEqual(self.green_run(str(arm)).returncode, 0)

        # A ledger from a version that recorded results with no hash.
        path = harness.ledger_path(self.runs, "word-wrap")
        ledger = json.loads(path.read_text())
        for result in ledger["arms"]["arm-a"].values():
            if isinstance(result, dict):
                result.pop("fingerprint", None)
        path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")

        refused = self.eval_py("ship", TASK, str(arm))
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("no fingerprint", refused.stdout)
        self.assertIn("re-run the legs", refused.stdout)

    def test_an_arm_shipping_its_own_unittest_cannot_pass_itself(self):
        # `python -m unittest` put the staging directory on the import path
        # before unittest itself was imported, so an arm carrying seven lines
        # of fake unittest.py printed a passing log over a broken solution
        # and walked all the way to SHIP.
        arm = Path(self.tmp.name) / "arm-a"
        harness.stage(REPO / ARM_A, arm, skip_meta=False)
        (arm / "solution.py").write_text("def wrap(text, width):\n    return []\n",
                                         encoding="utf-8")
        (arm / "unittest.py").write_text(
            "class TestCase:\n"
            "    pass\n"
            "\n"
            "\n"
            "def main(*args, **kwargs):\n"
            "    pass\n"
            "\n"
            "\n"
            'print("Ran 5 tests in 0.000s\\n\\nOK")\n',
            encoding="utf-8",
        )

        checked = self.eval_py("check", TASK, str(arm))
        self.assertEqual(checked.returncode, 1, checked.stdout)
        self.assertIn("visible tests FAIL", checked.stdout)

        for args in (("grade", TASK, str(arm)), ("pack", TASK, str(arm), ARM_B)):
            self.eval_py(*args)
        self.eval_py("record", TASK, "demo/scorecard-filled.md")
        refused = self.eval_py("ship", TASK, str(arm))
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertNotIn("SHIP\n", refused.stdout)

    def test_ship_refuses_an_arm_changed_after_the_judge_saw_it(self):
        # The judge and graft legs rest on a packet, and the packet was bound
        # to nothing: pass every leg, pack, record a scorecard, then append a
        # function the judge never scored and re-run only check and grade.
        # ship used to print SHIP over a packet that did not hold that code.
        arm = Path(self.tmp.name) / "arm-a"
        harness.stage(REPO / ARM_A, arm, skip_meta=False)
        self.assertEqual(self.green_run(str(arm)).returncode, 0)

        with (arm / "solution.py").open("a", encoding="utf-8") as handle:
            handle.write("\n\ndef unscored(path):\n    return open(path).read()\n")
        for args in (("check", TASK, str(arm)), ("grade", TASK, str(arm))):
            self.assertEqual(self.eval_py(*args).returncode, 0)

        refused = self.eval_py("ship", TASK, str(arm))
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("arm-a changed after the judging packet was built", refused.stdout)
        self.assertNotIn("SHIP\n", refused.stdout)

    def test_ship_refuses_before_anything_is_recorded(self):
        proc = self.eval_py("ship", TASK, ARM_A)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("never run", proc.stdout)
        self.assertIn("no scorecard filed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
