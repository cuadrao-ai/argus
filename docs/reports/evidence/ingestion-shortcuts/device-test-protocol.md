# Shortcuts physical-device test protocol

**No physical-device verification was performed in this session.** Every
behavior below is unproven until the founder runs it on a real iPhone and fills
in the evidence table. A simulator or VM cannot prove Wallet, Messages or
notification triggers (the Wallet trigger cannot even be configured there).

Setup: follow [setup.md](setup.md) against a non-production API with
`ARGUS_INGESTION_ENABLED=true` and a reconciliation sink wired (until wave 2,
every capture answers 503 `shortcuts_intake_unavailable`, which is itself
check 0 below). Use small real purchases. Do not paste the device token into
the evidence; record only the connection id.

## Record first

| Field | Value |
| --- | --- |
| Date and time zone | |
| iPhone model | |
| iOS version (Settings → General → About) | |
| Region and language (Settings → General → Language & Region) | |
| Card(s) and issuer(s) in Wallet (no numbers) | |
| Trigger name as shown in Shortcuts (Transaction / Wallet / other) | |
| Spanish UI labels seen (trigger, Run Immediately, actions) | |
| API base and connection id | |

## Checks

0. **No sink yet.** With wave 2 not wired, tap once: the shortcut shows "did
   not save" and the server answers 503. Nothing is listed for review.
1. **In-store tap, unlocked.** Expect one draft: merchant, card name, the
   amount text exactly as Wallet showed it, `status=unknown`,
   `direction=unknown`. Record the raw `amount` text (for example `RD$1,250.00`
   or `$1,250.00`) and whether Cuadrao resolved amount and currency.
2. **In-store tap, locked** (Express Mode or Face ID from the lock screen).
   Does the automation run before unlock, after unlock, or not at all?
3. **Online Apple Pay** (Safari) and **in-app Apple Pay**. Expected per
   secondary sources: no run. Record what happens.
4. **Offline.** Airplane mode, then tap. Does the shortcut stop with an error?
   Is the line kept in `pending.txt` (fallback)? Turn the network on, run
   "Send pending captures", and confirm exactly one draft appears.
5. **Same merchant, same amount, twice** within a minute (two real purchases).
   Expect **two** drafts with different `external_id`s.
6. **Re-send.** Run "Send pending captures" again with the same file. Expect
   receipts with `unchanged` and no new draft.
7. **Run Immediately.** Is "Run Immediately" available for the trigger without
   a confirmation prompt? Does a banner appear on each run?
8. **Delay.** Note the time between the tap and the shortcut running (watch
   for runs minutes or hours later, or none: the forum-reported timeout).
9. **Declined tap** (if it happens naturally): does the automation run?
10. **Dominican card** (BHD, Popular, Banreservas, Qik, Santa Cruz, Promerica
    or Scotiabank): does the trigger run at all, and how does Wallet format
    the amount (`RD$`, `$`, `DOP`)?
11. **Message trigger.** Bank SMS from the short code: does the automation run
    without confirmation, and does `text` arrive complete?
12. **iOS 27 notification trigger.** Is "When I receive a notification from"
    available for the bank app? Does it pass the notification text when the
    app hides previews or the phone is locked?
13. **Disconnect.** Disconnect the device in Cuadrao, then tap. Expect the
    shortcut's "did not save" notification and a 401 from the server, and the
    device's unreviewed drafts removed.

## Evidence table

| # | Result (pass / fail / not run) | Observed (raw amount text, timings, prompts) | Screenshot or log reference |
| --- | --- | --- | --- |
| 0 | | | |
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |
| 9 | | | |
| 10 | | | |
| 11 | | | |
| 12 | | | |
| 13 | | | |

After the run, update the labels in [capabilities.md](capabilities.md) from
"Device" or "Secondary" to "Physical device (date, iOS version)" only for the
claims actually observed.
