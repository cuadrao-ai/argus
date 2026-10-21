# Data-use register: how to read it

**Status:** DRAFT. Nothing reads this file today. Do not change product code from this document. A later slice may wire it.

[data-use-register.yaml](data-use-register.yaml) lists every data flow once. The privacy policy, the App Store worksheet and, later, in-product consent screens should all derive from it, so one fact lives in one place.

## Fields of each flow

| Field | Meaning |
| --- | --- |
| `id` | Stable name. Never reuse an id for a different flow. |
| `product` | `personal`, `personal_full`, `business` or `marketing`. A list means shared. |
| `data_categories` | What kinds of data move. |
| `purpose` | Why, in one sentence. |
| `recipient` | The subprocessor that receives data. |
| `sent` | What exactly leaves Cuadrao. |
| `retention` | How long, with `[A CONFIRMAR]` where unknown. |
| `training_use` | `to_confirm` until the provider's policy is confirmed for the exact model and route. `not_applicable` when no model provider is involved. Never write "no" without proof. |
| `consent.scope` | The existing consent owner. The names are the keys under `consent_scopes`. `none_required` means the data is needed to provide the service. `none_persisted` means no persisted consent exists in the repo yet. |
| `consent_text` | The text the person sees, in `es` and `en`. For the two WhatsApp scopes it is the product text copied from `src/argus/domain/ingestion/whatsapp/ai_consent.py`, 3 to 4 sentences long, and the code wins if the two differ. |
| `consent_text_short` | Only for the two WhatsApp flows: a proposed one-sentence version, not product text. |
| `consent_text_status` | `code` (copied from product code), `proposed` (written for this draft, not product text) or `none`. |
| `policy_anchor` | The section id in [privacy-policy.md](privacy-policy.md). Prefix `es-` or `en-`. |
| `sources` | Repo paths behind the claims. |

## How product code can read it later

1. Parse the YAML at build time. Do not parse it per request.
2. A consent screen looks up the flow by `id`, shows `consent_text[language]` and links to `privacy-policy` plus `es-`/`en-` and `policy_anchor`.
3. A test should fail when a flow with a `consent.scope` other than `none_required` has no entry in `consent_scopes`, or when a `consent_text` is empty for a flow that needs consent.
4. A test should fail when `consent_text` for a WhatsApp scope differs from the code constant. The register must follow the code, never the reverse.
5. A change to what is sent or to the provider changes the flow. Under the consent contract, a changed text or route asks the person again. The register change and the code change belong in the same PR.
6. Product code must not route intent by reading this file. It describes data use, it does not decide behavior.

Keep `[A CONFIRMAR]` markers visible until the question in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) is closed. A flow with an open marker must not appear as a published promise.
