# Apple Shortcuts capture: what iOS actually provides

**Date:** October 1, 2026. **Branch:** `claude/ingestion-shortcuts`.
**Scope:** MVEE [§4.6](../../../specs/argus-minimum-viable-ecosystem-experience.md#46-apple-pay--google-pay-and-device-assisted-capture)
under the [ingestion lane](../../../specs/lanes/financial-ingestion-connectors.md).
**Releases covered:** iOS 27 (current, released September 2026) and iOS 26.
iOS 17 and 18 are cited where the trigger was introduced or changed.

## How this was researched, and its limits

This session ran in a Linux container. The egress proxy blocked
`support.apple.com`, `apps.apple.com`, `discussions.apple.com`, Wikipedia and
every third-party blog fetched (MacStories, 9to5Mac, MacRumors, iGeeksBlog,
Matthew Cassinelli, Graham Haley, Expenses, WalletPal, Derek Seaman, Beard.fm).
Only `developer.apple.com/forums` pages could be read in full. Everything else
comes from search-engine result titles and snippets, so it is labeled
**secondary**. Apple Support page *titles* that appeared in results are cited
as evidence that the page exists, not as a reading of its content.

**No physical iPhone was used. A simulator or VM cannot prove any of this:**
the Wallet trigger cannot even be configured in the iOS Simulator (cards fail
to add and the automation's Next button stays disabled, per
[Apple Developer Forums 746889](https://developer.apple.com/forums/thread/746889)).

Labels: **Source** = read in full on the cited page. **Secondary** = from
search snippets or third-party reports, not read in full. **Device** = only a
physical iPhone can settle it; see the
[device test protocol](device-test-protocol.md).

## 1. Wallet "Transaction" trigger

| Claim | Label | Confidence | Citation |
| --- | --- | --- | --- |
| A personal-automation trigger for Wallet transactions was added in iOS 17 (named "Transaction") | Secondary | High | Apple Support page title "Transaction triggers in Shortcuts on iPhone or iPad" (support.apple.com/guide/shortcuts/apd65c67538a/ios); Matthew Cassinelli, "Shortcuts has new Automations in iOS 17 and iPadOS 17: Transaction, Display, & Stage Manager"; AppleInsider "How to use Shortcuts in iOS 17" |
| On iOS 26 the trigger appears as "Wallet" ("When I tap" a card or pass) instead of "Transaction" | Secondary | Medium-low (one third-party source) | GitHub pull request "the iPhone recipe names the trigger iOS actually has" (stefanogebara/twin-me #399, snippet only; the page later returned 404) |
| iOS 27 folds automations into the shortcut editor as stacked triggers; no report says the Wallet trigger's inputs changed | Secondary | Medium | MacStories iOS 27 review p.13; MacRumors "iOS 27 Makes the Shortcuts App Much Less Intimidating"; 9to5Mac 2026-09-29 (snippets) |
| Filters: which card or pass, which category, which merchants. Pass types include payment, transit, access and identity | Secondary | Medium-high | Cassinelli iOS 17 article (snippet); iDropNews iOS 17 |
| It fires for in-store contactless (NFC) Apple Pay, not for online/web Apple Pay | Secondary | Medium | Graham Haley "Apple Pay automation" ("NFC only, not from a web browser"); Threads post "does not work for online purchases" |
| In-app Apple Pay purchases | Device | Unknown | No source found either way |
| It fires for any card in Wallet, not only Apple Card | Secondary | Medium | Setup guides tell users to "select the cards you want"; forum reports cover Visa and Mastercard from various issuers |
| Some issuers' cards never fire (Mastercard from some issuers reported) | Source (user reports) | Medium | [Developer Forums 765516](https://developer.apple.com/forums/thread/765516) |
| It can fire for **declined** transactions | Source (user reports) | Medium | [Developer Forums 765516](https://developer.apple.com/forums/thread/765516) |
| It often times out and never runs when the issuer's transaction detail reaches Wallet late; regressed in iOS 18; reports continue to February 2026; Feedback FB14035016, FB16379100 | Source (user reports) | High that it happens; frequency unknown | [765516](https://developer.apple.com/forums/thread/765516), [758053](https://developer.apple.com/forums/thread/758053) |
| Apple Pay is available in the Dominican Republic (since August 2024) with BHD, Banreservas, Popular, Qik, Santa Cruz, Promerica and Scotiabank cards | Secondary | High | Forbes RD 2024-08-07; Scotiabank DO and Promerica DO Apple Pay pages (titles) |
| The trigger fires for Dominican-issued cards | Device | Unknown | Depends on whether the issuer sends transaction detail to Wallet |

### What the transaction input carries

| Variable | Label | Notes |
| --- | --- | --- |
| Amount | Secondary, high | A **formatted text**, not a number: guides tell users to strip the currency symbol and separators before using it (Graham Haley; BudgetBakers "Apple Pay Integration") |
| Currency | Secondary, high that there is **no separate currency variable** | No guide lists one; the currency only appears as a symbol inside the formatted amount. Whether that symbol is "$", "US$" or "RD$" for a given card and region setting is **Device** |
| Merchant | Secondary, high | Listed by every guide |
| Card or Pass (name) | Secondary, high | "Card or Pass" variable; the last four digits are **not** reported as a separate field |
| Name | Secondary, medium | Listed as a field; its exact meaning is unverified |
| Transaction time | Secondary, medium that there is **none** | No guide lists one; recipes use "Current Date" at run time, which is the run time, not the authorization time |
| Transaction type, status, settlement | Not provided | A tap is not proof of settlement (MVEE §4.6) |

### How it runs

| Claim | Label | Citation |
| --- | --- | --- |
| "Run Immediately" (no confirmation) is offered for this trigger | Secondary, high | Setup guides ("select Run immediately"); Cassinelli "All Automations Now Run Immediately In Shortcuts (Notifications Required)" |
| A banner may still show for privacy-sensitive triggers | Secondary, medium | Cassinelli (above); MacRumors iOS 15.4 notifications how-to |
| Runs while the iPhone is locked | Device | Wallet taps commonly happen with the phone locked (Express Mode); no source states whether the automation runs before unlock |
| "Get Contents of URL" with no network fails; Shortcuts has no built-in retry or outbox | Secondary, high (general Shortcuts behavior) | No source documents a retry; the recipe must handle failure itself |
| The trigger may also run long after the tap (delayed issuer data) or not at all | Source (user reports) | [765516](https://developer.apple.com/forums/thread/765516) |

## 2. Notifications from other apps (bank push alerts)

**Changed in iOS 27.** Up to iOS 26 there was no trigger on arbitrary
third-party app notifications (Secondary, high: no trigger list for iOS 17-26
includes one). Reviews of iOS 27 report a new trigger:

| Claim | Label | Confidence | Citation |
| --- | --- | --- | --- |
| iOS 27 adds "When I receive a notification from" a chosen app | Secondary | Medium-high (several independent outlets) | MacStories iOS 27 review p.13; 9to5Mac 2026-09-29; iGeeksBlog; iThinkDiff "Shortcuts in iOS 27"; TWiT "iOS Today 27 Shortcuts" (snippets) |
| Filters on Title, Subtitle and Message (up to three); a "Notification" variable exposes body text, time-sensitivity and date | Secondary | Medium | Beard.fm guide; MacStories (snippets) |
| It can run immediately | Secondary | Medium-low | Snippets say "take action immediately"; one says such triggers always show a banner |
| Bank apps that hide notification content, or apps excluded by Apple, still pass text | Device | Unknown | Not documented anywhere reachable |
| Works with the phone locked | Device | Unknown | |

The adapter accepts these as `source_app: "notifications"` message captures
(inert text, every money field unresolved). It never treats the trigger as a
universal bank feed.

## 3. Messages (bank SMS alerts)

| Claim | Label | Confidence | Citation |
| --- | --- | --- | --- |
| A "Message" communication trigger exists (iOS 17+), filtering by Sender and/or "Message Contains" | Secondary | High | Apple Support page title "Communication triggers in Shortcuts on iPhone or iPad" (apdd711f9dff); MacMost auto-reply guide; forward-sms.com setup guide |
| It can be set to Run Immediately | Secondary | Medium-high | Same snippets ("one of the automations that can be run automatically without asking for confirmation") |
| The message is passed as Shortcut Input and its text can be sent with "Get Contents of URL" | Secondary | Medium | SMS-forwarding products are built on exactly this (forward-sms.com; zhgchg.li SMS forwarding article) |
| Fires for SMS from short codes that Dominican banks use | Device | Unknown | |

## 4. Storing a secret in a shortcut

| Claim | Label |
| --- | --- |
| A token pasted into a Text action is plain text: anyone holding the unlocked phone can open the shortcut and read it | Secondary, high (how Text actions work) |
| Sharing a shortcut (iCloud link or file) exports its Text actions, including the token. Shortcuts may offer to strip "import questions", but a hard-coded Text value is shared as is | Secondary, medium |
| There is no Keychain-backed secret store reachable from Shortcuts without a native app's App Intent | Secondary, medium |

Design consequences in the adapter:

- The device token is one random 256-bit value per device, shown once, stored
  server-side only as a SHA-256 digest. Its only power is adding unconfirmed
  drafts to that person's review; it cannot read anything.
- Disconnecting the device in Cuadrao deletes the digest and ends the
  connection, so a leaked or shared token stops working at once.
- The setup guide tells the person never to share the shortcut and to
  disconnect and re-enroll if they did.

## 5. What this means for the product (no overclaiming)

- Wallet capture is opt-in, per card, and best effort: it misses online
  purchases, some issuers, and delayed or timed-out triggers, and it can fire
  for declined taps. Statements and bank alerts remain the completeness path.
- A tap is evidence with `status=unknown`, `direction=unknown`, and a currency
  only when the formatted amount names one unambiguously.
- Notification and SMS captures are inert text for review; no money field is
  extracted in this wave.
- A later native App Intent (Swift, Keychain-held token, real retry queue)
  would remove the token-in-Text-action exposure. That is a decision for the
  iPhone delivery owner and is not part of this wave.
