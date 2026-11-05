# Document extraction fixtures

Six documents cover receipt totals, Spanish DOP/USD debit and credit columns,
a two-page statement, repeated equal purchases, balances and unreadable content.
These are evaluation inputs, not evidence of Dominican-bank compatibility.
The public examples are receipts. The statements are fictional.

`manifest.json` holds independently reviewed financial expectations and SHA-256
checksums. Production extraction must receive only document bytes and upload
metadata, never the answer manifest or original labels. Missing dates and
currencies remain null. A receipt contributes one purchase total; its item
prices, tax, cash tender and change are not separate transactions.

## Public receipt attribution and license

The two receipts are test rows 0 and 1 from the official
[naver-clova-ix/cord-v2 dataset](https://huggingface.co/datasets/naver-clova-ix/cord-v2).
The [CORD authors' repository](https://github.com/clovaai/cord) links this exact
v2 dataset and licenses the work under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
The upstream license is preserved in `LICENSE-CORD.txt`.

Credit belongs to Seunghyun Park, Seung Shin, Bado Lee, Junyeop Lee, Jaeheung Surh,
Minjoon Seo and Hwalsuk Lee, *CORD: A Consolidated Receipt Dataset for Post-OCR
Parsing*, 2019. The source revision is
`7f0115a4b758a71d6473b8d085751692da2fef98`.

The official dataset viewer supplied JPEG derivatives and original
`ground_truth` JSON. Both are retained unchanged. Financial expectations are
new evaluation annotations. The two row URLs, revision and checksums are in
the manifest. Retrieval used the public endpoint below, followed by each row's
image URL. The image URLs are temporary, so they are not committed.

```text
https://datasets-server.huggingface.co/rows?dataset=naver-clova-ix%2Fcord-v2&config=default&split=test&offset=0&length=2
```

## Pair validation

Both public images were visually inspected against their original labels.
Image dimensions, split and image IDs agree. Every original word quadrilateral
falls within the matching image. Total label boxes contain nonuniform image
pixels and their strings agree with `gt_parse.total.total_price`.

- Test 0 visibly prints `TOTAL (Qty 2.00) 60.000`. Its total amount box is
  `(280, 532, 368, 555)` in a 432 by 648 image. The expectation reads the dot as
  thousands grouping and records 60000.00. The printed discount, tax and
  subtotal do not form a trustworthy arithmetic reconstruction. The visible
  grand total owns the amount. No explicit currency or readable date survives.
- Test 1 visibly prints three item amounts 17500, 46000 and 27500, totaling
  91000. Its total amount box is `(539, 826, 813, 867)` in a 960 by 1280 image.
  CASH repeats the same total and is not a second transaction. The image's
  third item reads `Y.BASO PROM`. Item text is not used as a financial
  acceptance label.

All three synthetic PDF pages were rendered with Poppler and visually checked.
`pdftotext -layout` independently verifies the date, description, amount,
currency header and page for every expected transaction. Opening balance plus
credits less debits equals closing balance in each statement. USD deliberately
has both an opening balance and a real income of 100.00; identical amounts
alone cannot distinguish them. The synthetic receipt image visibly totals
DOP 250.50. The unreadable image hides all transaction pixels under an opaque
rectangle and expects zero rows.

These checks validate the document/label pairing, not an extraction model.
The six examples are a small convenience sample, not a representative accuracy
estimate. Synthetic PNGs are photo-like renderings, not actual camera photos.
For duplicate-upload verification, send the exact same document bytes again.

## Local reproduction

The renderer extends the deterministic PDF layout and Pillow approach from
`tests/synthetic_ingestion/renderers.py`; existing samples and demos are untouched.
The checked-in synthetic source owns rendering instructions. Expected rows are
kept separately in the manifest and checked against the actual rendered output.

```bash
.venv/bin/python scripts/documents/prepare_fixtures.py
.venv/bin/python -m pytest tests/document_extraction_fixtures --confcutdir=tests/document_extraction_fixtures --no-cov -q
```

Twelve checks passed locally. Pillow is required. Poppler's `pdftotext` is required
for the two PDF pair checks; missing Poppler produces an explicit skip.
Generation uses no network, credentials or models. The public images are
preserved inputs and are not re-downloaded by the renderer.
