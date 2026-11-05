# Keep the staging WhatsApp pilot usable

Use the existing Cuadrao number, app, webhook, and approved Business owner.
Use synthetic receipt data for acceptance. The owner selects the Business and
sender that retain the pilot connection.
Keep the approved staging connection after acceptance. The release owner handles
credentials, dashboard actions, publication, staging configuration, and release.

The authoritative runtime secret is `CUADRAO_WHATSAPP_ACCESS_TOKEN` in the
`cuadrao-api-staging` service's Environment panel. The owner uses
`/Users/garces/.cuadrao/staging-secrets.env` for secure handoff. That file is not
the runtime authority. Never source, copy, or read it into a developer worktree.
Confirm the receiving-number binding in the owner dashboard. A configured display
number alone does not prove that binding.

## Check the connection once

1. Record the approved staging API and web commit IDs.
2. Read back the effective intake configuration in the staging runtime. Keep secret
   values out of commands, evidence, logs, and chat. Do not source a local secrets file.
3. Run the offline configuration check through the pinned project runtime.

   ```bash
   poetry run python scripts/ops/check_whatsapp_pilot.py
   ```

4. If a credential check is approved, run it once inside that staging runtime.

   ```bash
   poetry run python scripts/ops/check_whatsapp_pilot.py --probe-credential
   ```

   The check makes one read-only request for the configured number ID. It uses the
   existing server credential and requests no discovery permission. It follows no
   redirect and performs no retry. Each network phase has a five-second timeout.
   The check rejects a response when a received chunk would put the total over
   64 KiB or when processing passes ten seconds, checked between chunks.
   An active network read can take up to its timeout to return.

5. To inspect delivery failures, export a bounded staging JSONL log window. Record
   its start and end times with the evidence. Pass the export to the same check.

   ```bash
   poetry run python scripts/ops/check_whatsapp_pilot.py --events temp/pilot-events.jsonl
   ```

   The export can contain at most 1 MiB. The check reads it without echoing raw
   records. Protect the export and delete it after review if it contains private
   application logs. A `whatsapp_delivery_failed` event contains only a safe
   numeric `graph_code` and a fixed `failure_reason`.

6. Read each result separately. `configuration=configured` confirms the intake
   switch and required values are present. `credential.status=authorized` confirms
   current number access. Neither result proves a callback, media download, draft,
   web visibility, credential type, scope, expiry, or final message delivery.
7. If no failure event exists, keep delivery `unverified`. Quiet traffic and an empty
   export are not failures. An observed callback can still contain only statuses.
8. If the check exits with code 2, follow its fixed `actions`. Exit code 0 means no
   actionable problem was found in the checks performed. It is not pilot acceptance.

## Rotate or recover the server credential

1. Have the release owner confirm the credential belongs to the approved server
   system user, app, and messaging account. Use the already known dashboard IDs.
   Grant only the access required for the existing number and receipt path.
2. Record actual expiry and data-access expiry from the dashboard or an approved
   credential inspection. Record absent expiry as absent, never as permanent access.
   A number-access request cannot establish expiry or credential type.
3. If code `190` has subcode `463`, replace the expired credential. Subcode `464`
   concerns the token user's unconfirmed account state, not completed Business
   verification. It does not require reopening Business verification or repairing
   an old personal backup before installing the approved server credential.
   Other `190` failures require validity and revocation checks. For a permission
   denial, check the approved app, account, and number assignments.
4. Update only the existing staging access-token secret through the approved secret
   store. Read back presence without revealing its value. Keep the verify token,
   app secret, sender key, and owner link intact unless a separate repair needs them.
5. Batch the credential update and required restart into the reviewed, deliberate
   manual staging API release. Media and reply transports capture their credential
   at startup. An environment edit alone does not replace them. This procedure
   does not authorize a separate restart or deployment.
6. Run one credential preflight. Record the result with the staging revision.
7. If the replaced credential is still valid, have its owner revoke it only when
   separately approved. Prove that rejection once through the approved private
   inspection. If it is already expired, retain the existing expiry evidence and
   clean up the obsolete copy without a redundant revocation or probe. Do not put
   either credential in evidence or use a receipt as a credential probe.

## Recover a receipt without a second extraction

1. Inspect the existing receipt in the correct owner's Business Inbox before any
   resend. An HTTP 200 webhook response means inbound claims were committed.
   Background media work can still fail after that response.
2. If the inbound claim is `received`, let its active processing window finish.
   A stale claim or a settled `failed` claim does not guarantee another callback.
   Do not fabricate or replay a webhook payload and do not change database state.
3. If no receipt exists after a confirmed capture failure, repair the named cause.
   Ask the approved sender to resend the original bytes once. Provider replay uses
   its existing message claim. A new message with identical bytes uses the existing
   receipt identity in that Business and does not start an extra extraction.
4. If the receipt is `saved`, it is unread. With shared Business receipt reading off,
   capture saves it without a model call. Turning reading on does not by itself
   reread a duplicate. Use the existing owner preparation action if a read is wanted.
5. If reading is on when a new receipt arrives, capture queues it and dispatches
   reading automatically after acknowledgement. Consent is checked again before
   the model call. The owner does not need to press Prepare for this path.
6. If the receipt is `queued` or `preparing`, inspect its existing preparation state.
   If an attempt has an unknown provider outcome, use the established owner-consented
   recovery. Never start an automatic retry or promise that a second call is free.
7. If it is `review_ready` or `needs_attention`, open that receipt and review it.
   A failed acknowledgement or later outbound delivery failure does not undo capture.
   Repair the delivery cause without resubmitting the receipt or extraction.

## Prove one complete receipt path

1. Confirm the dashboard publication, callback, messages subscription, credential,
   receiving number, persistent staging configuration, and visible web entry gates.
   After valid metadata confirms the binding, record the verified receiving number
   in the release owner's private binding and acceptance artifact. Never substitute
   an unverified display setting for that proof.
2. Confirm the approved sender is linked to the intended owner's open Business.
   Record the current shared receipt-reading state and the bounded read allowance.
3. Have that sender send one fresh synthetic receipt to the existing Cuadrao number.
4. Prove the signed callback, authenticated media read, matching source checksum,
   intended Business, one reviewable draft, and its visible Inbox row at the recorded
   staging revisions. Keep capture, extraction, and outbound delivery evidence separate.
5. Perform the agreed replay or same-byte resend check. Confirm one receipt and one
   extraction attempt. Stop before financial approval. An outbound API acceptance
   proves request acceptance only. Confirm final delivery independently if required.
6. Remove only temporary exports, local test data, and temporary test access that
   the owner approved for removal. Keep the approved credential, persistent sender
   link, webhook subscription, and staging flags. Read back that state after cleanup.
7. Record the next manual credential inspection before the actual expiry, or after
   a reported failure or access change. Do not create agent wake-ups or polling jobs.
