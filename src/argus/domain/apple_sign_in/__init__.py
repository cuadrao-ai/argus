"""Sign in with Apple: the server side of token revocation.

App Store Review Guideline 5.1.1(v) requires an app that offers Sign in with
Apple to revoke the person's Apple tokens when they delete their account. The
native app signs in through Supabase Auth with Apple's identity token; Supabase
never sees a refresh token in that flow, so revocation is Argus's job.

- ``config``: the Apple client secret inputs, read from the environment. Any
  missing piece fails closed.
- ``client_secret``: the ES256 JWT Apple accepts as ``client_secret``.
- ``client``: the bounded HTTP client for Apple's token and revoke endpoints.
- ``credentials``: capture (exchange the one-time authorization code and keep
  only the sealed refresh token) and revoke (what the account-deletion lane
  calls). The repository has an in-memory twin and a Postgres implementation.
"""
