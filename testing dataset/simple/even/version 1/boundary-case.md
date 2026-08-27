# CSV importer retirement — Edge / boundary case — version 1

Fixture path: simple/even/version 1  
Captured: 2026-08-03  
Domain: Atlas migration portfolio  
Document type: Change record / review evidence  
Owner: Maya Chen

## Situation

This boundary fixture tests a narrow scope: replace the legacy vendor CSV upload with a signed JSON drop, with only enough evidence to verify under 90 seconds for a 25 MB import. Missing evidence must be reported as unknown.

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

