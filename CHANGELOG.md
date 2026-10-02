# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added packaging, so `pipx install git+https://github.com/eliferres/agent-eval-harness` puts one command, `agent-eval`, on your path; it takes the same subcommands as the module and `agent-eval --version` prints the version. Anything the tool prints about what to run next names the command you invoked, `agent-eval` or `agent_eval.py`.

### Fixed
- A test run now gets 300 seconds. An arm that hangs used to hold the harness open until something outside killed it, which in CI means a job burning to the runner's limit with no verdict; it is now killed at the limit and its leg reads "timed out". The limit is documented under Limitations.
- A ledger file that is valid JSON but not a ledger is now refused with one line at exit 2, the way a corrupt one already was, instead of crashing on whichever key was read first.
- A file in an arm the harness cannot read now gives one line on standard error and exit 2, the exit code the tool documents for bad input, instead of a raw traceback at exit 1.
- An arm can no longer rewrite the hidden tests it is judged by. The test child was handed the caller's whole environment, working directory included, so an arm could walk to the checkout and overwrite the fixture, which poisoned every later run of every arm. The child's environment no longer names a working directory, and `check` and `grade` hash the task's visible and hidden tests before the run and refuse with one line at exit 2 if they moved.
- A test leg that ran no tests is now red. `check` and `grade` decided a leg on the child process's exit status alone, so an arm that ends the run before the first test does, and a test directory nothing is discovered in, both printed PASS with a count of 0 and reached SHIP at exit 0. A leg with a count of zero, or a ledger row carrying no count, is refused.
- A copy of a hidden test parked inside an arm's `__pycache__` directory is now caught. The contamination check reads every file in the arm, build residue included, rather than the staging view that leaves residue out, so `grade` refuses the arm instead of clearing it and letting its hidden leg go green.
- An arm that ships its own `unittest.py` no longer answers for its own test run. `check` and `grade` now run the tests from a clean directory with the real `unittest` imported before the arm's files are reachable, so a fake pass printed by a file inside the arm cannot stand in for the result. A broken solution that used to print a passing log and reach SHIP now fails the visible leg.
- `ship` no longer trusts a result recorded against code that has since changed. Every test leg and the judging packet store a sha256 over the arm's file names and bytes, and `ship` recomputes them for the arm you name and for every arm the packet holds, since the scorecard is a comparison and replacing the loser's code leaves the winner's judgement describing neither side. An arm edited after a leg passed or after the packet the judge scored was built is refused with a non-zero exit naming the arm and what it outran. A result or packet stored without that hash is refused as unverifiable, with a line saying what to re-run. `ship` also checks that the directory you name is the directory the legs were run against, resolved, so a copy of an arm made somewhere else cannot answer for the original.
- `ship` no longer trusts a result recorded against tests that have since changed. An arm graded against a one-test hidden set, with the real hidden tests put back afterwards, printed SHIP at exit 0 while `grade` on the same arm said FAIL. Every test leg now also stores a sha256 of the test folder it ran, and `ship` refuses with a line naming the folder and the leg when it no longer matches. A result recorded by an earlier version carries no such hash and is refused as unverifiable until the legs are re-run.
- `record` now refuses a scorecard whose `Judge` line is blank or still holds its placeholder, and one whose title names a different task, with one line and exit 2. Both used to be filed at exit 0, though the README says unfilled placeholders are refused, so a card written for another task could unblind this one.
- `grade` now warns on standard error about every `.py` file in the hidden tests that test discovery will never run: one not named `test*.py`, such as `wrap_edges_test.py`, or one in a subfolder with no `__init__.py`. Such files were skipped silently, so one trivial test left beside them carried the hidden leg to green. The README states the naming rule.
- `record` now refuses a scorecard whose winner is scored below the other submission, with one line giving both scores, and exit 2. A card scoring the arms 3 and 9 and naming the 3 the winner used to be filed, and that arm's judge leg then went green under a floor of 8. A tie is still accepted.
- An arm that sits anywhere under a directory named `__pycache__` is now read as the files it holds. The skip list was matched against the whole path, so such an arm staged nothing for the tests and cleared the contamination check without one of its files being read.
- An empty file in an arm is no longer reported as a copy of the hidden tests. Blank lines are normalized away before the comparison, so an ordinary empty `__init__.py` beside an empty one in the hidden tests made `grade` refuse the arm and left its hidden leg red whatever the arm did. Files that normalize to nothing are skipped on both sides.
- A bad task fixture or scorecard path now writes its one error line to standard error, not standard output, so it cannot land in a report that captures what the tool printed. The exit code is still 2.
- `check`, `grade`, `pack` and `ship` now refuse an arm path that is not a directory with one line on standard error and exit 2. A typo used to run the tests against an empty staging directory and write a ledger row for a directory that is not there, build a one-armed judging packet whose blind comparison held one submission, and print a four-leg card that reads as an arm which was evaluated and failed.
- The demo transcript and the terminal picture in the README now come from a real run of every command the walkthrough shows, both `ship` runs included, and are held there by a test that replays the session on every CI run, so nothing the README shows can drift from what the tool prints.

### Changed
- The README now states what the harness defends against and what it does not. The opening promise that it "refuses to ship until all four legs are green" is replaced by what the tool does: each arm's tests in a separate process, every result and the judging packet bound to a hash of the arm's files, and `ship` refusing its word while a leg is missing, red or recorded against code that has changed since. It also says plainly that this is not a sandbox, because an arm's code runs in the same process as the test runner that judges it and an arm written to defeat that can, and points anyone grading submissions they do not trust at a container. The Limitations point about running an arm's code is rewritten to name that limit instead of one narrow mechanism.
- Reshaped the README around the run itself: the sections are now Try it, How a run works, A run on the demo task, Scorecard format and What ship refuses, the file layout is one paragraph under Try it instead of a table, and the license is one closing line. The walkthrough now takes one arm all the way through, `check` then `grade`, before starting the other, instead of grouping both arms under each command. The text under each heading is the text that was there.
- Renamed `eval.py` to `agent_eval.py` and `harness.py` to `eval_harness.py`, so installing this tool cannot shadow another package that owns the generic top-level name `eval` or `harness`.

## [1.1.0](https://github.com/eliferres/agent-eval-harness/releases/tag/v1.1.0) - 2026-09-03

### Added
- Added a terminal demo to the README's first screen, showing eval.py check and grade against a passing arm and against an arm whose hidden test catches a bug the visible tests never probed.
- Added a test for a judge tie and a test for an arm the ledger has never seen, bringing tests to 0.53x source lines.
- Added macos-latest to the CI matrix alongside ubuntu-latest.

### Changed
- Added the missing return type hint to `iter_files()`, the one function in harness.py that had none.

## [1.0.0](https://github.com/eliferres/agent-eval-harness/releases/tag/v1.0.0) - 2026-08-31

First public release.
