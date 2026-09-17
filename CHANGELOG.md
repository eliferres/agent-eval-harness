# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added packaging, so `pipx install git+https://github.com/eliferres/agent-eval-harness` puts one command, `agent-eval`, on your path; it takes the same subcommands as the module and `agent-eval --version` prints the version.

### Fixed
- `ship` no longer trusts a result recorded against code that has since changed: every leg stores a hash of the arm's files, `ship` recomputes it, and an arm edited after its legs passed is refused with a non-zero exit naming the arm and the leg. A result stored without that hash is refused as unverifiable, with a line saying to re-run the legs.

### Changed
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
