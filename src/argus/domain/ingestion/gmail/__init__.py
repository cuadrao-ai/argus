"""Gmail connector: authorized, read-only retrieval of financial email.

The person connects a mailbox through Google OAuth (``gmail.readonly`` only)
and chooses which bank senders to import from. Matching messages become
``ImportCandidate`` drafts through the hub's ``CandidateSink``; nothing here
creates accounts or activity, and no message content is interpreted by a model
or a keyword rule in this wave.

Evidence: docs/reports/evidence/ingestion-gmail/README.md
"""
