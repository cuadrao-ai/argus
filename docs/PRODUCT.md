# Cuadrao product overview

Cuadrao is a Spanish-first web app for small businesses in the Dominican Republic and their accountants. It turns receipts and invoices into reviewed records and the 606/607 reports.

The [README](../README.md) describes the current product. The [pilot review spec](specs/cuadrao-pilot-review-spec.md) owns Bandeja, the receipt dossier and month close. It separates approved behavior from the evidence needed to call it done.

## Current workflow

Documents arrive by upload, forwarded email or WhatsApp. Cuadrao reads their facts for review. Unapproved receipts stay in Bandeja. Approved records live in Registros. Inicio counts what needs attention.

The owner or accountant can review and correct a record. Only the owner role can approve it. Nothing is approved automatically. In the pilot, the accountant holds the Dueño seat for the client business. That setup does not grant approval to the accountant role.

Payment and collection are separate from approval. Approved records produce the 606 and 607 reports. Amounts keep the document's currency. The reports declare DOP only. Foreign-currency lines stay marked as awaiting a rate, without conversion.

<a id="current-production-availability-and-planned-changes"></a><a id="4-product-principles"></a>

## Archived product direction

The personal iOS and Android apps are archived. Personal and household finance, chat and guest entry are no longer current product direction. Chat is being removed, and the Business app has no guest mode. Remaining legacy code does not restore those features to the product scope.

The [documentation authority map](DOCUMENTATION_AUTHORITY.md) separates current contracts from historical specs and reports. Keep those records as history. Their former launch plans, feature flags and chat behavior do not assign new work.
