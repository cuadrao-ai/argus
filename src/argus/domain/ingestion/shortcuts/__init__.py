"""Apple Shortcuts connector: Wallet taps and message captures as evidence.

A person enrolls a device, pastes its token into a shortcut, and each run
posts one event. Events become unconfirmed ``ImportCandidate`` drafts through
the hub's sink; nothing here creates accounts or activity.

Capabilities and limits: docs/reports/evidence/ingestion-shortcuts/capabilities.md
"""
