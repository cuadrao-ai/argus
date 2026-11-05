# Confirmed deletion cleanup boundary

Base: `8146d16e90633eb543781f8882665482f0d5dca9` (#875 landed).

The existing deletion command journals a completed per-user obligation before
retiring proof. Receipt readback derives from that record. The old public
acknowledgement checks identity and removes the record, but the caller must clear
files first. A can complete, then B can adopt before that external cleanup begins.
The old caller clears A's directory; acknowledgement then rejects the stale
receipt. The rejection is too late to prevent the filesystem effect.

## Usage and selected signature

```swift
try await controller.acknowledgeConfirmedAccountDeletion(receipt) { userID in
    try cleanupExactUserDirectory(userID)
}
```

The callback is required, synchronous, throwing and `@Sendable`. It receives the
validated journal UUID, not whichever account is currently visible. The actor
acquires its existing mutation guard, validates absent session/pending proof and
all receipt/journal fields, invokes cleanup, then removes that user's completed
record. There is no suspension between validation, cleanup and removal. Do not
hold the credential-storage lock while invoking an app callback.

The callback-free public signature is removed. The completed journal remains the
only cleanup retry obligation. Cleanup failure leaves it intact. Acknowledgement
storage failure after successful cleanup also leaves it intact, so the callback
must tolerate a missing directory on retry. The API cannot prove that caller code
cleans the correct files; the later app adapter must provide its exact-user,
idempotent throwing cleanup implementation.

## Alternatives and synthesis

Two bounded read-only sketches compared (1) requiring cleanup on the existing
acknowledgement and (2) replacing it with a new finish command. Both put the same
validation and effect inside the existing actor. Keep the existing name and
require the callback: renaming adds caller churn without a different safety
boundary. A receipt-shaped callback was also considered. Passing only the
validated UUID gives the future filesystem adapter the fact it needs while
keeping command and epoch metadata inside the session owner.

An async callback or external cleanup-then-ack sequence would allow actor
reentrancy between admission and the effect. A second cleanup marker would
duplicate the existing completed journal. Both are excluded.

## Callers and proof plan

The executable package caller is migrated. The #875 live SDK harness is immutable
historical evidence, not an active package caller. A migrated copy is retained
under this new slice's evidence and must be independently exercised at the new
source. No app receipt store, Application Support path or presentation is edited.

Prepare baseline proof using a synthetic filesystem caller on #875's source:
A completes, B signs in, the external caller removes A, then the old API rejects.
The prepared fixture must run before that is called a reproduced runtime result.

New package cases use only unique temporary directories. They check stale A/B
files stay unchanged; active B adoption rejects cleanup before effects; completed
cleanup and missing-directory retry; callback failure retains the record;
successful cleanup followed by acknowledgement-storage failure remains retryable
without another deletion POST; and pending 202, uncertainty and ordinary sign-out
cannot authorize cleanup. Identity checks use the existing journal, not a second
store. Source review and static checks are not runtime proof.
