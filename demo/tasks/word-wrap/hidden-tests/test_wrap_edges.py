"""Hidden tests: the implementer never sees these.

One test per edge the SPEC names. Each is a rule someone can read in the
spec and still fail to implement, which is exactly what a visible suite
stops measuring the moment it becomes the target.
"""

import unittest

from solution import wrap


class WrapEdgeTest(unittest.TestCase):
    def test_over_long_word_is_never_broken(self):
        self.assertEqual(wrap("a supercalifragilistic b", 5), ["a", "supercalifragilistic", "b"])

    def test_whitespace_runs_collapse(self):
        self.assertEqual(wrap("  a\t\tb \n c  ", 5), ["a b c"])

    def test_whitespace_only_text_returns_no_lines(self):
        self.assertEqual(wrap("   \n\t ", 8), [])

    def test_width_one_puts_each_short_word_on_its_own_line(self):
        self.assertEqual(wrap("a b c", 1), ["a", "b", "c"])

    def test_width_below_one_raises(self):
        with self.assertRaises(ValueError):
            wrap("anything", 0)


if __name__ == "__main__":
    unittest.main()
