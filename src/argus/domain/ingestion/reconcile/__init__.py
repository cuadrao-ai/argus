"""Reconciliation: the single owner between connector evidence and the ledger.

It implements ``CandidateSink`` for every connector, groups observations of
the same real-world event, keeps distinct purchases distinct, holds the review
queue, and writes canonical activity only through ``MoneyService`` after the
person confirms. Spec: docs/specs/lanes/financial-ingestion-connectors.md
"""
