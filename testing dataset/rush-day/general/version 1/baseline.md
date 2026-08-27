# production outage response — Normal operating case — version 1

- Fixture: rush-day/general/version 1
- Domain: Atlas migration portfolio
- Document type: Requirements / PRD
- Owner: Priya Raman · Site Reliability
- Decision date: 2026-08-03

## Intent

The approved objective is to restore the document-preview API after a certificate rotation broke workers. Success is measured by restore previews and establish a verified rollback within 60 minutes.

## Scope

In scope are the API contract, migration metrics, a rollback condition, and a named human reviewer. Out of scope are unrelated platform redesigns and any claim not supported by this document.

## Evidence to collect

1. Verify the baseline count and the target metric.
2. Link the architecture decision to the implementation path.
3. Compare the latest status with this approved intent.
4. Gate final changes with an item-level human decision.

## Acceptance criteria

A grounded deliverable cites this heading and the exact source filename. A missing or conflicting value becomes a finding, not a guess.

Source integrity: synthetic fixture with no confidential data.

