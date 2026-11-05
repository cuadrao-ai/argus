"""Financial recording domain: accounts and their confirmed records.

The first slice owns account creation, reopening, editing and opening-balance
corrections. Rules live here; storage lives in the repositories; HTTP lives in
the router. See ``docs/specs/lanes/financial-accounts-first-slice.md``.
"""
