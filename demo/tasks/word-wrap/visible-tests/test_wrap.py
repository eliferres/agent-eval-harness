"""Visible tests: the implementer may run these while working.

They cover the shape of the task, not its edges. The edges live in
hidden-tests/ and are what the grader actually decides on.
"""

import unittest

from solution import wrap


class WrapTest(unittest.TestCase):
    def test_packs_greedily(self):
        self.assertEqual(
            wrap("the quick brown fox jumps", 10),
            ["the quick", "brown fox", "jumps"],
        )

    def test_exact_fit_stays_on_one_line(self):
        self.assertEqual(wrap("abc de", 6), ["abc de"])

    def test_single_word_shorter_than_width(self):
        self.assertEqual(wrap("hello", 10), ["hello"])

    def test_empty_text_returns_no_lines(self):
        self.assertEqual(wrap("", 10), [])

    def test_every_line_fits_the_width(self):
        text = "one two three four five six seven eight nine ten"
        for line in wrap(text, 12):
            self.assertLessEqual(len(line), 12, line)


if __name__ == "__main__":
    unittest.main()
