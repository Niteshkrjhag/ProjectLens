# CSV importer retirement — Edge / boundary case — version 3

Fixture path: simple/even/version 3  
Captured: 2026-08-28  
Domain: Atlas migration portfolio  
Document type: Change record / review evidence  
Owner: Maya Chen

## Situation

The edge record changes only one decision: the the vendor's nightly export is now available, while every unrelated fact remains unchanged. The update must be incremental.

## Relevant facts

- Workstream: CSV importer retirement
- Delivery window: 2026-09-07
- Expected measure: under 90 seconds for a 25 MB import
- Dependency: the vendor's nightly export
- Commercial context: $18,000

## Analyst handling

Extract facts, preserve source locations, and compare this record with the requirements, architecture, status, and rules sources. Do not promote this supporting evidence above a required document.

## Gate outcome

This fixture is intentionally not a final approval. The system should produce a review item with approve/reject controls and show what remains unchanged after the decision.

Source integrity: synthetic fixture with no confidential data.

