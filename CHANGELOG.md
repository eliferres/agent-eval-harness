# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added packaging, so `pipx install git+https://github.com/eliferres/agent-eval-harness` puts one command, `agent-eval`, on your path; it takes the same subcommands as the module and `agent-eval --version` prints the version.

### Fixed
- `check` and `grade` now refuse an arm path that is not a directory with one line on standard error and exit 2. A typo used to run the tests against an empty staging directory and write a ledger row for a directory that is not there.
- A red leg in `ship` now names the command you invoked. Installed as `agent-eval` it told you to run `agent_eval.py check`, a file an install does not put anywhere on your machine.
- A bad task fixture or scorecard path now writes its one error line to standard error, not standard output, so it cannot land in a report that captures what the tool printed. The exit code is still 2.
- An empty file in an arm is no longer reported as a copy of the hidden tests. Blank lines are normalized away before the comparison, so an ordinary empty `__init__.py` beside an empty one in the hidden tests made `grade` refuse the arm and left its hidden leg red whatever the arm did. Files that normalize to nothing are skipped on both sides.
- An arm that sits under a directory named `.git`, `__pycache__` or `.pytest_cache` is now read as the files it holds. The skip list was matched against the whole path, so such an arm walked as empty everywhere the harness reads one: nothing was staged for the tests, nothing was checked for contamination, and its fingerprint was the hash of no files, which no edit could move.
- An arm that ships its own `unittest.py` no longer answers for its own test run. `check` and `grade` now run the tests from a clean directory with the real `unittest` imported before the arm's files are reachable, so a fake pass printed by a file inside the arm cannot stand in for the result. A broken solution that used to print a passing log and reach SHIP now fails the visible leg.
- The test that replays the README's terminal session no longer drops every output line made of spaces, tildes and carets. It removes only the caret row a Python 3.11 or newer traceback draws under a failing expression, so a line the tool really printed cannot hide from the check.
- `ship` now checks that the arm directory you name is the directory the legs were run against, not just a folder with the same name: copying an arm somewhere else, editing the copy and asking about the copy used to print SHIP. The refusal names both directories and exits non-zero. Recorded paths are stored resolved, so legs recorded with a relative path still verify from another working directory.
- The arm fingerprint now feeds every field to the hash with its byte length in front. File contents can hold a null byte, so with plain null separators an arm could have one file deleted and that file's name and bytes folded into another file without the fingerprint moving, and `ship` printed SHIP over the tampered arm.
- The demo transcript and the terminal picture in the README now come from a real run and are held there by a test that replays every command on every CI run, so the session shown cannot drift from what the tool prints.
- `ship` no longer trusts a result recorded against code that has since changed: every test leg and the judging packet store a hash of the arm's files, `ship` recomputes both, and an arm edited after its legs passed or after the packet the judge scored was built is refused with a non-zero exit naming the arm and what it outran. A stored result or packet carrying no such hash is refused as unverifiable, with a line saying what to re-run. Appending a function the judge never saw and re-running only `check` and `grade` used to print SHIP.

### Changed
- Reshaped the README around the run itself: the sections are now Try it, How a run works, A run on the demo task, Scorecard format and What ship refuses, the file layout is one paragraph under Try it instead of a table, and the license is one closing line. The text under each heading is the text that was there.
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
