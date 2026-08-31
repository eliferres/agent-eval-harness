# Contributing

Welcome things:

- Task fixtures in other languages, with the runner change they need.
- Stronger contamination checks, with a test showing what they catch
  that the content hash does not.
- Fixes to anything the README claims that turns out not to be true. The
  walkthrough is executable; if a line of it is wrong, that is a bug.

Ground rules: the harness stays stdlib-only and never calls a model,
arms stay opaque directories, and every change keeps
`python3 -m unittest discover -s tests` green. Structural proposals
belong in an issue before a PR; the pattern here is deliberately small,
and most feature ideas are better as forks.
