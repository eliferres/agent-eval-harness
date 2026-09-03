# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added a terminal demo to the README's first screen, showing eval.py check and grade against a passing arm and against an arm whose hidden test catches a bug the visible tests never probed.
- Added a test for a judge tie and a test for an arm the ledger has never seen, bringing tests to 0.53x source lines.
- Added macos-latest to the CI matrix alongside ubuntu-latest.

### Changed
- Added the missing return type hint to `iter_files()`, the one function in harness.py that had none.

## [1.0.0](https://github.com/eliferres/agent-eval-harness/releases/tag/v1.0.0) - 2026-08-31

First public release.
