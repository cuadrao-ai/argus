"""Plaid connector: Link, transaction sync, webhooks, reconnect and revoke.

It only observes. Provider rows become ``ImportCandidate`` evidence handed to
the hub's ``CandidateSink``; nothing here touches canonical financial activity.
Access tokens are server-side only, sealed through ``IngestionHub.box``.

Spec: docs/specs/lanes/financial-ingestion-connectors.md
Evidence: docs/reports/evidence/ingestion-plaid/README.md
"""
