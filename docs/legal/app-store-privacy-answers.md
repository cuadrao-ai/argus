# App Store privacy worksheet for Cuadrao Personal

**Status:** DRAFT worksheet, not submitted answers. Derived from [data-use-register.yaml](data-use-register.yaml). The final answers need the release profile, the actual enabled providers and the signed archive's SDK manifests. Apple's questions and guideline numbers are as the [privacy preflight](../reports/2026-10-05-cuadrao-privacy-preflight.md) reviewed them on October 5, 2026. [A CONFIRMAR: re-read Apple's current pages before submission]

Legend: **Collected** = we or a partner receive it off the device. **Linked** = tied to the person's account. **Tracking** = used to track across other companies' apps or sites. Cuadrao does not track in the Apple sense. [A CONFIRMAR: no advertising SDK or data broker use, check at the release candidate]

## Answers per data type

| Apple data type | Collected | Linked to user | Used to track | Purpose (Apple term) | Register flows |
| --- | --- | --- | --- | --- | --- |
| Contact info: email address | Yes | Yes | No | App functionality | personal_account_identity |
| Contact info: name | Yes, if given | Yes | No | App functionality | personal_account_identity |
| Identifiers: user ID | Yes | Yes | No | App functionality, analytics | personal_account_identity, product_analytics |
| Financial info: other financial info (balances, plans, debts) | Yes | Yes | No | App functionality | personal_financial_records |
| User content: other user content (chat, notes) | Yes | Yes | No | App functionality | personal_chat_ai, personal_full_agent |
| User content: photos or videos (chosen receipt photos) | Yes, when uploaded | Yes | No | App functionality | personal_document_extraction |
| User content: other (documents, PDFs) | Yes, when uploaded | Yes | No | App functionality | personal_document_extraction |
| Location: precise or coarse (receipt location) | [A CONFIRMAR: only if sent off device] | Yes | No | App functionality | none yet, see OPEN_QUESTIONS |
| Usage data: product interaction | Yes | [A CONFIRMAR: the actor is a keyed hash, do not answer "not linked" only because of the hash] | No | Analytics | product_analytics |
| Diagnostics: crash and performance data | [A CONFIRMAR: depends on the tracing configuration] | [A CONFIRMAR] | No | App functionality | hosting_and_logs |
| Audio data (live voice) | [A CONFIRMAR: only if voice ships] | Yes | No | App functionality | none yet |
| Purchases: purchase history | [A CONFIRMAR: only if the Full tier ships; Apple handles payment] | [A CONFIRMAR] | No | App functionality | personal_subscription |

Not collected, per the current code: health, fitness, browsing history, search history, contacts, sensitive info. [A CONFIRMAR at the release candidate]

## Third-party AI disclosure (App Review guideline 5.1.2(i))

Apple requires the app to say clearly what personal data is sent to third-party AI and to get explicit permission before sending it.

| Item | Draft answer |
| --- | --- |
| Who receives data | OpenRouter and the model providers behind it (chat, receipt reading, memory check), Perplexity (finance research, memory embeddings). [A CONFIRMAR: final list for the release] |
| What is sent | Chat text and context, chosen documents and photos, candidate memory text, search queries. See each flow's `sent` field. |
| Why | To answer, to read receipts into drafts, to remember facts. |
| Permission | Required before the first send. Today the repo has persisted permission only for WhatsApp in Business and per-document extraction. Personal chat and memory have no persisted shared permission yet (issue 828). This is a release blocker for Personal. |
| Withdrawal | Stops later requests. Cannot recall data already sent. |
| Training use by providers | To confirm per model. Do not state "not used for training" until confirmed. |

Draft in-app wording is in each flow's `consent_text`. Personal chat and memory text are placeholders until the consent design is chosen.

## Other release items this worksheet touches

- Privacy policy URL and in-app link while signed in: [A CONFIRMAR: URL].
- Account deletion in the app: required by guideline 5.1.1. The [privacy policy](privacy-policy.md#en-retention) describes it.
- Privacy manifest and SDK manifests: the retained packaging evidence covers a past baseline only. A final signed archive must be checked again.
- Sign in with Apple and Google: both are off in Release builds today. Answer for the providers that ship.

## Sources

[Privacy preflight, App Store section](../reports/2026-10-05-cuadrao-privacy-preflight.md), [data-use-register.yaml](data-use-register.yaml), [privacy-policy.md](privacy-policy.md).
