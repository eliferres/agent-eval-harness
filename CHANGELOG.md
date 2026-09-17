# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added packaging, so `pipx install git+https://github.com/eliferres/agent-eval-harness` puts one command, `agent-eval`, on your path; it takes the same subcommands as the module and `agent-eval --version` prints the version. Anything the tool prints about what to run next names the command you invoked, `agent-eval` or `agent_eval.py`.

### Fixed
- An arm that ships its own `unittest.py` no longer answers for its own test run. `check` and `grade` now run the tests from a clean directory with the real `unittest` imported before the arm's files are reachable, so a fake pass printed by a file inside the arm cannot stand in for the result. A broken solution that used to print a passing log and reach SHIP now fails the visible leg.
- `ship` no longer trusts a result recorded against code that has since changed. Every test leg and the judging packet store a sha256 over the arm's file names and bytes, `ship` recomputes both, and an arm edited after a leg passed or after the packet the judge scored was built is refused with a non-zero exit naming the arm and what it outran. A result or packet stored without that hash is refused as unverifiable, with a line saying what to re-run. `ship` also checks that the directory you name is the directory the legs were run against, resolved, so a copy of an arm made somewhere else cannot answer for the original.
- An arm that sits under a directory named `.git`, `__pycache__` or `.pytest_cache` is now read as the files it holds. The skip list was matched against the whole path, so such an arm staged nothing for the tests and cleared the contamination check without one of its files being read.
- An empty file in an arm is no longer reported as a copy of the hidden tests. Blank lines are normalized away before the comparison, so an ordinary empty `__init__.py` beside an empty one in the hidden tests made `grade` refuse the arm and left its hidden leg red whatever the arm did. Files that normalize to nothing are skipped on both sides.
- A bad task fixture or scorecard path now writes its one error line to standard error, not standard output, so it cannot land in a report that captures what the tool printed. The exit code is still 2.
- `check` and `grade` now refuse an arm path that is not a directory with one line on standard error and exit 2. A typo used to run the tests against an empty staging directory and write a ledger row for a directory that is not there.
- The demo transcript and the terminal picture in the README now come from a real run and are held there by a test that replays every command on every CI run, so the session shown cannot drift from what the tool prints.

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
