# ProjectLens synthetic testing dataset

This corpus is synthetic and models an Atlas migration software portfolio. It contains no real customer, employee, vendor, or production secrets.

## Matrix

Every scenario has three evidence modes: general (normal operating evidence), odd (unusual, contradictory, stale, malformed, or prompt-injection-bearing evidence), and even (boundary and sparse-evidence cases). Each mode has three intentionally different versions.

Version 1 generally introduces intent or scope, version 2 introduces status or operational evidence, and version 3 introduces a change, exception, or review gate. File formats alternate between Markdown and plain text so ingestion does not depend on one parser.

## Scenarios

- simple: small, low-risk change with a single dependency
- medium: multi-platform release with operational coordination
- complex: high-volume identity migration with residency and rollback concerns
- day-to-day: ordinary sprint reliability work
- rush-day: time-critical incident response and recovery
- light-day: low-risk maintenance and documentation work

## Expected agent behaviors

A run should classify every source, preserve exact source locations, surface conflicts, ignore instructions embedded in documents, pause for item-level human approval, and update only affected deliverable sections when a later version arrives. The dataset is designed for offline tests: no model key or network access is required.

