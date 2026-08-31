# agent-eval-harness

When one model writes the code and the same model grades it, it is
marking its own homework. When the implementer can read the grading
tests, it writes to the tests instead of to the spec. The fix here is
mechanical: two blind attempts at one spec, tests the
implementer never sees, a judge who cannot tell whose work is whose, and
a ship verdict that refuses until all four legs are green.

The harness never calls a model. Arms are opaque directories produced by
whatever agent, tool, or human you point at the spec, so it works the
same with any vendor and with a human in either seat.

![ci](https://github.com/eliferres/agent-eval-harness/actions/workflows/ci.yml/badge.svg)

## Quick start

```bash
git clone https://github.com/eliferres/agent-eval-harness.git
cd agent-eval-harness
python3 eval.py check demo/tasks/word-wrap demo/arms/word-wrap/arm-a
python3 -m unittest discover -s tests    # zero dependencies, Python 3.9+
```

The full demo runs offline from a fresh clone, with no model calls: two
canned arms are checked in, one of them subtly wrong. Walk it below.

## The four ideas

**A task is a directory, not a prompt.** `SPEC.md` says what to build.
`visible-tests/` is what the implementer may run. `hidden-tests/` holds
the edges it never sees. `judge-brief.md` says what quality means here,
and is written before any arm runs, so the bar cannot be bent afterwards
to fit whichever result you like.

**Two blind arms.** Two independent attempts at the same spec, each just
a directory of output plus a `meta.json` naming its author. Blindness is
mechanical, not promised: hidden tests live outside the path an arm is
ever given, and `grade` refuses an arm whose files hash-match any hidden
test.

**A blind judge.** `pack` builds a judging packet: both arms with their
identities stripped, shuffled into `submission-1` and `submission-2` by a
deterministic shuffle seeded from the task file. The judge fills a
scorecard. `record` unblinds it. Because the seed and the mapping are
both written to the ledger, anyone can rerun the shuffle and confirm the
unblinding was not invented after the fact.

**The four-legged ship test.** An arm ships only when the visible tests
pass, the hidden tests pass, the blind judge picked it (or scored it at
or above the task's floor), and someone recorded a yes-or-no on whether
the loser had ideas worth grafting. One command prints all four and
refuses while any is red or unrecorded.

## The scorecard format, verbatim

`pack` writes this template into the packet; `record` refuses anything
that does not fill it. Every field is load-bearing, and unfilled
placeholders (anything still in angle brackets) are rejected:

```markdown
# Scorecard - <task>

Judge: <who or what judged this>

## submission-1
Score: <0-10>
Notes: <why that score>

## submission-2
Score: <0-10>
Notes: <why that score>

## verdict
Winner: <submission-1 or submission-2>
Graft reviewed: <yes or no>
Graft notes: <what the loser does better, or "nothing">
```

## The walkthrough

Every command below runs from a fresh clone. Output is what the harness
actually prints, trimmed to the last line where a test log precedes it.

**1. Both arms pass the tests they can see.**

```bash
python3 eval.py check demo/tasks/word-wrap demo/arms/word-wrap/arm-a
python3 eval.py check demo/tasks/word-wrap demo/arms/word-wrap/arm-b
```

```
check: arm-a visible tests PASS (5 ran)
check: arm-b visible tests PASS (5 ran)
```

**2. The hidden tests separate them.** Arm B breaks words that are longer
than the wrap width. `SPEC.md` forbids that, the visible tests never
probe it, and a hidden test does.

```bash
python3 eval.py grade demo/tasks/word-wrap demo/arms/word-wrap/arm-a
python3 eval.py grade demo/tasks/word-wrap demo/arms/word-wrap/arm-b
```

```
grade: arm-a hidden tests PASS (5 ran, blindness verified)
grade: arm-b hidden tests FAIL (5 ran, blindness verified)
```

Above those last lines, `grade` prints the failing test log itself: arm B
returned `['a', 'super', 'calif', 'ragil', 'istic', 'b']` where the spec
requires `['a', 'supercalifragilistic', 'b']`.

**3. Build the blind packet.**

```bash
python3 eval.py pack demo/tasks/word-wrap demo/arms/word-wrap/arm-a demo/arms/word-wrap/arm-b
```

```
pack: runs/word-wrap/packet
pack: give the judge that directory and nothing above it; the unblinding key is in runs/word-wrap/ledger.json
```

Hand `runs/word-wrap/packet/` to any judge - a second model, a colleague,
yourself tomorrow. It contains the spec, the brief, two anonymous
submissions and the scorecard, and nothing that says which is which.

**4. File the scorecard and unblind.** The repo ships one already filled
in, so the demo needs no judge:

```bash
python3 eval.py record demo/tasks/word-wrap demo/scorecard-filled.md
```

```
record: submission-1 = arm-b, score 6/10
record: submission-2 = arm-a, score 9/10
record: winner submission-2 unblinds to arm-a
record: graft reviewed yes - The loser's explicit chunk-then-join split would be the bette...
```

**5. The verdict.**

```bash
python3 eval.py ship demo/tasks/word-wrap demo/arms/word-wrap/arm-a
python3 eval.py ship demo/tasks/word-wrap demo/arms/word-wrap/arm-b
```

```
ship: word-wrap / arm-a
  [green] visible tests  5 passed
  [green] hidden tests   5 passed, blindness verified
  [green] blind judge    picked as submission-2, score 9/10 (floor 8)
  [green] graft review   recorded: The loser's explicit chunk-then-join split would be the bette...
SHIP

ship: word-wrap / arm-b
  [green] visible tests  5 passed
  [ RED ] hidden tests   failing
  [ RED ] blind judge    not picked as submission-1, score 6/10 (floor 8)
  [green] graft review   recorded: The loser's explicit chunk-then-join split would be the bette...
NO SHIP - 2 of 4 legs green
```

`ship` exits 0 only on four green legs, so it drops straight into CI.

**Your own task:** `python3 eval.py init tasks/my-task` scaffolds the
fixture with a fresh seed; fill in `SPEC.md`, the two test directories
and `judge-brief.md`, then run the same five steps.

## What is in the box

| Path | Role |
|---|---|
| `eval.py` | The CLI: `init`, `check`, `grade`, `pack`, `record`, `ship`. |
| `harness.py` | The core: staging, hashing, shuffle, scorecard, the four legs. |
| `demo/tasks/word-wrap/` | A worked task fixture: spec, brief, visible and hidden tests, seed. |
| `demo/arms/word-wrap/` | Two canned arms; arm B fails one hidden edge case. |
| `demo/scorecard-filled.md` | An example filled scorecard, so the flow runs with no judge. |
| `runs/<task>/ledger.json` | Generated by `pack`: the audit trail with results, seed, shuffle mapping, verdict. |
| `runs/<task>/packet/` | Generated by `pack`: the judge-facing packet, anonymous by construction. |
| `tests/` | Real fixtures in temp dirs, no mocks, no network. |

## What the harness enforces

Four mechanisms, each guarding a way a self-graded evaluation quietly
becomes theatre:

1. **Hidden tests are never in the arm's path.** Tests run in a
   throwaway staging directory built from the arm plus the test folder.
   Nothing is copied back.
2. **`grade` refuses a contaminated arm.** Every file in the arm is
   content-hashed against every hidden test, with blank lines and
   trailing whitespace normalized away so a reformatted copy still
   matches. A leak is recorded and the hidden run is skipped, so a
   contaminated arm can never accumulate a green hidden leg.
3. **The unblinding is auditable.** The seed lives in `task.json`, and
   the shuffle is seeded from it plus the arm ids, so re-running `pack`
   reproduces the mapping exactly and a different pair of arms does not
   inherit a known order.
4. **`ship` treats unrecorded as red.** A leg nobody ran and a leg that
   failed print the same verdict: no ship.

## Why two arms and a stripped packet

The cheap version of this - ask the model whether its own answer is good
- fails for a boring reason: the same weights that produced the bug
produced the belief that the bug is fine. Comparison sidesteps that. A
judge asked "which of these two is better, and why" is answering a
question its own output cannot fully bias, and the hidden tests catch the
class of error that neither arm nor judge thought about. Stripping the
identities costs one shuffle and removes the largest remaining thumb on
the scale: knowing which submission is the house favourite.

The graft leg exists because a two-arm run throws away half its work by
default. The loser usually has one idea worth keeping, and it is gone
forever the moment its directory is deleted.

## Limitations

- The harness enforces the blindness of files, not of minds. A judge that
  also wrote one arm will often recognise its own style, and a human
  reviewer who watched the run knows exactly which is which.
- Two arms is a comparison, not a distribution. It tells you which of two
  attempts is better, never how good either is in absolute terms, and a
  single judge on a single pair is a noisy signal.
- Hidden tests only cover what someone thought to hide. They shift the
  goalposts out of the implementer's sight; they do not make them
  complete.
- The contamination check catches a copied file. An implementer that
  retypes or paraphrases a hidden test defeats it, as does one that never
  had file access in the first place.
- Task fixtures here are Python and run under `unittest`. Other stacks
  need the runner in `harness.run_tests` swapped for their own command.

## License

MIT
