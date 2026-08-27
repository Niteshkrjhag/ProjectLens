# production outage response — Edge / boundary case — version 1

Fixture path: rush-day/even/version 1  
Captured: 2026-08-03  
Domain: Atlas migration portfolio  
Document type: Change record / review evidence  
Owner: Priya Raman

## Situation

This boundary fixture tests a narrow scope: restore the document-preview API after a certificate rotation broke workers, with only enough evidence to verify restore previews and establish a verified rollback within 60 minutes. Missing evidence must be reported as unknown.

## Relevant facts

- Workstream: production outage response
- Delivery window: 2026-08-28
- Expected measure: restore previews and establish a verified rollback within 60 minutes
- Dependency: the managed certificate provider
- Commercial context: incident

## Analyst handling

Extract facts, preserve source locations, and compare this record with the requirements, architecture, status, and rules sources. Do not promote this supporting evidence above a required document.

## Gate outcome

This fixture is intentionally not a final approval. The system should produce a review item with approve/reject controls and show what remains unchanged after the decision.

Source integrity: synthetic fixture with no confidential data.

