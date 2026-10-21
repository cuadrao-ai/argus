# Legal drafts: open questions

Every fact the drafts could not confirm. Owner: founder, lawyer, accountant or engineering. Close a question here, then replace its marker in the documents.

## Placeholders used

`{{OPERADOR_LEGAL}}`, `{{DIRECCION_LEGAL}}`, `{{PAIS_DE_CONSTITUCION}}`, `{{CONTACTO_PRIVACIDAD}}`, `{{CONTACTO_SOPORTE}}`, `{{FECHA_DE_VIGENCIA}}`, `{{EDAD_MINIMA}}`.

## Questions

| # | Question | Owner | Where it appears |
| --- | --- | --- | --- |
| Q1 | Legal entity name, address and country of formation. The company is not formed yet. Governing law and forum depend on it. | Founder, lawyer | All documents |
| Q2 | Contact addresses for privacy and support. The marketing site already shows `hola@cuadrao.ai` (see the forms contract). Is that the legal contact too? | Founder | Privacy 1, 10, 14, 18; Terms |
| Q3 | Where does Supabase store the data (region) and where does Render host it? Which plan and backup window apply? | Founder (engineering reads the hosted settings) | Privacy 9, 11; Business B12 |
| Q4 | Is Business B2B only? If a sole proprietor or consumer can use it, consumer rules may apply. | Founder, lawyer | Business terms intro |
| Q5 | Ley 172-13 (Dominican data protection): is registration or notice required? What are the breach duties and deadlines? Which other laws apply to users in other countries? | Lawyer | Privacy 10, 12; Business B10, B11 |
| Q6 | Meta's view of the WhatsApp agent: does the policy for business messaging allow an AI agent that talks to the owner? Which opt-in and template rules apply? | Founder, lawyer | Privacy 5; Business B6 |
| Q7 | For every model in use on OpenRouter, what are the provider's retention and training policies? Which route and data-collection setting do we use? The register marks every model flow `to_confirm`. | Engineering with founder | Register `training_use`; Privacy 4 |
| Q8 | Does a query-only DGII delegation exist that lets Cuadrao check an e-CF or NCF automatically? Until then every value stays "not verified". | Accountant | Business A5 |
| Q9 | WhatsApp phone-number consent: exact wording for the owner linking a number, and for the people who message the number if any. The Spanish text of the agent permission (scope 1) is only a proposed translation, since the code has English only. | Lawyer, founder | Register `business_whatsapp_capture`, `business_whatsapp_agent`; Privacy 5 |
| Q10 | The 10 year fiscal record duty: exact period and rule, who must keep what, and whether Cuadrao may delete a Business's records on account deletion. The repo records the Business retention rule as still open. | Accountant, lawyer | Privacy 9; Business B8, B9 |
| Q11 | How does the type 32 consumer invoice (e-CF) relate to the B02 rule the repo records? What is its amount limit and its ITBIS and ISR treatment? | Accountant | Business A6 |
| Q12 | Is the paid Full tier sold by Apple in-app purchase? Price, periods, free trial, price-change notice, what the agent includes, what happens to data after cancelling. The repo has no purchase implementation and says subscriptions are hidden. | Founder | Personal terms 2, 8; Privacy 15 |
| Q13 | Personal AI consent: a persisted, versioned permission for chat, memory check, embeddings and research does not exist yet (issues 818, 826, 828). Needed before release under Apple guideline 5.1.2(i). | Founder, engineering | Register; App Store worksheet |
| Q14 | Which providers are really active at launch (Perplexity, Google sign-in, Apple sign-in, push, voice)? Remove the rest from the policy. | Founder | Privacy 4, 8 |
| Q15 | Retention for logs (Render), analytics (PostHog), email (Resend) and WhatsApp media at Meta. | Founder (engineering reads settings) | Privacy 9; register `retention` |
| Q16 | Cookies and consent: the Argus web policy says no banner is needed. Does that hold for Cuadrao pages, and for the marketing site's signup consent text? | Lawyer | Privacy 13, 14 |
| Q17 | Minimum age and rules for minors. | Lawyer | Privacy 16; Personal terms 4 |
| Q18 | Is "we do not sell your information or use it for targeted advertising" safe against the real provider settings? | Lawyer | Privacy 3 |
| Q19 | Encryption of connected-source credentials: the held draft says it, the current code owners were not checked. Is any connected source (Gmail, Plaid) shipping? | Engineering | Privacy 12 |
| Q20 | Does receipt location leave the device? Needed for the App Store answer. | Engineering | App Store worksheet |
| Q21 | Where are these documents published (URLs), and how do they replace the Argus web policy, given the held draft's pending item P6? | Founder | App Store worksheet |
| Q22 | Does counsel review before the beta, and which documents are mandatory first? | Founder | All |
| Q23 | Firm-level accountant delegation (a later phase): the terms and data roles for a firm. | Founder, lawyer | Business B5 |
| Q24 | The WhatsApp receipt-reading permission text in `ai_consent.py` (RECEIPT_SCOPE) says the model reads "merchant, amount and date", but the extractor also reads RNC, NCF, e-CF and ITBIS (`src/argus/domain/ingestion/documents/extractor.py`). The permission text needs a code change in a separate PR, and the consent re-asks after it. Standard 12 covers model-facing prompts and schema field descriptions; `RECEIPT_SCOPE` is consent copy shown to the person and is not sent to the model, so Standard 12 does not apply to it (unverified: check that no prompt reuses the string). Consent text rules and counsel review apply instead. This PR does not touch product code. The register and policy describe what is really read. | Engineering, founder | Register `business_whatsapp_receipt_reading`; Privacy 4 |
| Q25 | Should accountants or firms be able to approve? Today only the owner approves; a grant to anyone else carries read and prepare only (`src/argus/domain/business/access.py:29-30`). An earlier draft statement that an accountant grant includes approve is superseded. | Founder (decision pending), lawyer | Privacy access section; Business B5 |

## Held draft reconciliation

The held draft on `docs/legal-cuadrao-deletion` (PR 781) has pending items P1 (Sign in with Apple), P4 (entity), P5 (support address), P6 (publication), P7 (retention numbers) and P8 (counsel). They map to Q14, Q1, Q2, Q21, Q15 and Q22. Its claim "deletion is final after one confirmation" is replaced here by the recoverable-operation wording from the privacy preflight. If PR 781 lands, merge the two sets of documents so only one file owns each text.
