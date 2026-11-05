"""Connected-source ingestion: one candidate contract, one reconciliation owner.

Connectors (Plaid, Gmail, Apple Shortcuts, statements) only *observe*. They turn
provider data into ``ImportCandidate`` evidence and hand it to a
``CandidateSink``. They never create, edit or remove canonical financial
activity; that remains ``recording.money_service.MoneyService``'s job, reached
only through the reconciliation owner after the person reviews.

Spec: docs/specs/lanes/financial-ingestion-connectors.md
"""
