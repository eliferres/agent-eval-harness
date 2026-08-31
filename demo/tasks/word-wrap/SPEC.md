# Task: word-wrap

Write `solution.py` exporting one function:

```python
def wrap(text: str, width: int) -> list[str]:
```

It breaks `text` into lines no longer than `width` characters.

## Rules

1. Words are runs of non-whitespace. Any run of whitespace (spaces, tabs,
   newlines) separates words and is otherwise discarded.
2. Greedy packing: each line holds as many words as fit, joined by a
   single space, without exceeding `width`.
3. A word longer than `width` is never broken. It occupies a line of its
   own, over-long, and does not share that line with any other word.
4. No line has leading or trailing whitespace, and no line is empty.
5. Text that is empty or all whitespace returns `[]`.
6. `width` below 1 raises `ValueError`.

## Out of scope

Hyphenation, justification, unicode width, and anything to do with I/O.
Return the lines; do not print them.
