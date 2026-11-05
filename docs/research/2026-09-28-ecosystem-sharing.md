# Ecosystem sharing through the Contagious framework

September 28, 2026. **Parked by the founder pending evidence of what people want to share.**
The proposal below is retained as research, not an active implementation task.
Household invitations and selected-file ingestion remain separate approved work.
The existing mobile archive remains unchanged. MVEE owns approved experience;
this note proposes a bounded extension rather than reopening the full design.

## Evidence and interpretation

Reviewed Jonah Berger's official [framework resources](https://jonahberger.com/contagious-resources/),
[workbook](https://jonahberger.com/wp-content/uploads/2013/03/Crafting-Contagious-Workbook.pdf),
and [reading guide](https://jonahberger.com/wp-content/uploads/2013/01/CONTAGIOUS_RGG_FINAL.pdf).
This is not a claim to have read the complete book. The framework includes Social
Currency, Triggers, Emotion, Public, Practical Value and Stories. It explains
more than status alone. The founder's Wordle, Strava and Wrapped examples are
inspiration; this review does not establish that those companies used the book
or that a sharing feature guarantees their growth.

The following applications are Argus recommendations, not findings from Berger:

| Principle | Argus application |
| --- | --- |
| Social currency | Let someone express follow-through, curiosity or preparedness through a milestone or a useful explanation. Avoid wealth rankings. |
| Triggers | Offer sharing at a completed goal or optional quincena/month review, with a quiet action rather than repeated prompts. |
| Emotion | Support pride and relief when a user recognizes progress. Do not manufacture anxiety or shame about money. |
| Public | Provide an intentional, minimal artifact with modest Argus attribution, while financial records remain private. |
| Practical value | Let a recipient understand a sourced explanation or comparison without signing up; offer a separate way to try it with their own inputs. |
| Stories | Give the user room to express what the milestone means, without inventing a testimonial or causal claim. |

## Suggested first experience

Reuse one share-preview flow for two artifacts:

1. A personal goal milestone, derived from recorded progress, such as “Moving
   fund complete.” Offer a generic title because goal names themselves can be
   sensitive. Never call scheduled contributions completed savings.
2. A selected useful answer or comparison. Preserve material assumptions,
   source dates/citations and limitations. Any backtest is labeled as a
   historical simulation; a cash projection is labeled as an estimate.

Entry is a quiet Share action on the relevant detail/result. The owner previews
exactly what will leave Argus, chooses permitted details, then uses the native
share sheet to export an image or an explicitly created read-only snapshot link.
Do not automatically publish on completing a goal. Dismissal changes no record.

Default exports omit amounts, account/merchant names, notes, financial-space
names, partner identity and source documents. Showing an amount is explicit.
Exclude household-derived milestones from the first public-share implementation
until participant consent and export permissions are defined; permission to view
shared records is not permission to publish them. Temporary chats retain their
separate retention/export boundary and are not automatic share sources.

Use the existing immutable, sanitized public-excerpt direction for links, with
owner revocation and no access to underlying records or conversation identifiers.
Revoking a hosted link cannot recall an exported image or someone else's copy.
A recipient can read the artifact without joining; “Try with my numbers” starts
with the recipient's own inputs and never copies the sender's private context.

## Growth loop and scope

Public artifact → recipient finds it useful → recipient tries Argus → records
or understands their own finances → has a meaningful result worth sharing.
This is a proposed acquisition loop, not a proven network effect. Household
collaboration has a direct shared-use benefit: inviting a partner improves
coordination for both participants. Neither loop requires a public social feed.

Keep plain household invites as approved. Defer annual recaps, leaderboards,
contact-network discovery, referral rewards, automatic posting and return-based
competitions. A reliable milestone and useful explanation are enough to test
the premise without turning the ecosystem into a social network.

Before implementation, define artifact permission/retention contracts and
acceptance for preview, cancellation, export failure, revoked links and recipient
entry. Suggested measures are completed shares, recipient reads, and recipients
reaching a useful first outcome; share-sheet opening alone is not a completed
share. No analytics implementation or sensitive financial event payloads are
authorized by this research note.
