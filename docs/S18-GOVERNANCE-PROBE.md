# S18 Governance Probe

This branch exists only to prove that a pull request with a deliberately failing required CI check cannot merge through the normal protected-main path.

The accompanying backend test is intentionally failing. This branch must never merge into `main`; after GitHub records the failed check and rejects a merge attempt, the pull request must be closed.
