# Cuadrao constitution source package

**Received:** October 4, 2026. **Status:** Preserved sources and reconciled principles index.
**Integration baseline:** `76b6afcb4080c6e639e8c50bdabf51621d862190`.

The founder supplied these three documents and requested a principles package to
guide future canonical documentation. This package preserves the originals and
makes their relationship to existing decisions explicit. Uploading or merging
this package does not approve every proposal, add launch requirements, or change
runtime contracts.

## Read in this order

1. [Principles index](PRINCIPLES.md) links to the adopted rules in their canonical owners.
2. [Reconciliation](RECONCILIATION.md) records conflicts, the governing decisions and their settled treatment.
3. Consult the original sources for detail and rationale.

| Original document | Contribution | Readable companion |
| --- | --- | --- |
| [GTM vision](Cuadrao_GTM_Vision.docx) | Audience, customer jobs, separate consumer and business tracks, commercial hypotheses | [Existing source transcript](../2026-10-04-cuadrao-gtm-vision-source.md) |
| [Product and business architecture](Cuadrao_Product_Business_Architecture.docx) | Space boundaries, shared services, records, business and fiscal workflows | [Existing source transcript](../2026-10-04-cuadrao-product-business-architecture-source.md) |
| [Feature and build quality guide](Cuadrao_Feature_and_Build_Quality_Guide.docx) | Workflow acceptance, failure recovery and a proposed feature catalog | [Text extraction](QUALITY-SOURCE.md) |

The two existing transcripts retain their original provenance. They are not
new transcriptions certified against these DOCX bytes. Use the uploaded DOCX
for exact wording, tables, diagrams and layout. The quality extraction preserves
paragraph and table-cell text in reading order, with tables flattened.

The originals are unedited. [SHA256SUMS](SHA256SUMS) records their byte hashes.
From this directory, verify them with `shasum -a 256 -c SHA256SUMS`.

## Authority and promotion

The [documentation authority map](../../DOCUMENTATION_AUTHORITY.md) still owns
which canonical document answers each question. This folder is a supporting
source package, not a second product authority or execution board.

The founder authorized the canonical reconciliation after the source upload.
The principles index now links to those owners. Future changes should cite the
reconciliation row and change the existing owner. Do not copy the same
rule into several owners. An unresolved product choice needs an explicit founder
decision before promotion. Technical contracts still need scoped design and
verification; business hypotheses still need customer evidence.

The [consumer launch tracker](https://github.com/lagarcess/argus/issues/817)
retains its assigned scope. The catalog's NOW, LATER and SKIP labels are source
recommendations, not ticket assignments or release gates. Regulatory deadlines,
provider eligibility, licensing and pricing in the originals are dated research
claims, not verified by this upload.
