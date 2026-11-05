# Issue #689: deterministic cache reproduction

Original integration: `61ef59d12f0f38ab3df507712e02f17991bedced`.
All requests and answers below are synthetic; providers are mocked.

## Cause and reachability

`research_tools.screening` puts `criteria` and `universe` into the query.
`grounded_result` includes those values, subject names/order, period, source
requirements, scenario guidance, and effective country/currency in the prompt.
Retrieval configuration also depends on shape, question kind, closed-window
status, scenario, language, location, and finance-tool coverage.

The previous `_cache_key_for` used only capability, shape, sorted symbols,
lowercased period/message, language, contract, and country. It omitted inputs
that changed the prompt or retrieval policy. Sorting symbols and lowercasing
arbitrary text could also erase distinctions that the provider still received.
The `|`/`,` serialization did not preserve field boundaries structurally.

Inline reads and writes used this key. Thorough requests serialized it, and
both the synchronous completion fallback and background poller trusted it in
`store_research_packet_for_job`. The cache is process-local: TTL expiry, bounded
oldest-entry eviction, and the test-only `cache_clear` are its invalidation
paths. There is no hosted research cache to purge.

Discovery separately keyed on message, anchors, and language even though its
provider receives `_search_query(request)`, which depends on relationship,
asset-class universe, category, and anchor order. Extraction and voicing happen
after the shared SearchResultPacket, independently for each request.

## Failing reproduction before the fix

The new `test_freeform_requests_do_not_reuse_or_store_answers` ran against the
original runtime. All eight cases failed:

| Synthetic change | Observed old behavior |
| --- | --- |
| Criteria above 10% → above 20% | Second request served first answer; one mocked provider call |
| Technology → healthcare universe | Same collision |
| Effective USD → DOP currency | Same collision |
| Open → closed window | Same collision despite different retrieval policy |
| Different period start date | Same identity despite different source-selection bound |
| Public-source requirement changes | Same identity |
| Different period description | Separate call, but unrestricted answers still entered shared storage |
| Identical free-form request | Shared storage accepted answer without public-only provenance |

The regression asserts two fresh mocked calls and no shared entries. Separate
private-input cases put a synthetic account marker in the message, criteria,
or universe and return it in provider prose. Citations and hashing do not make
that material eligible for sharing.

## Bounded fix and tradeoff

Grounded inline and thorough answers bypass shared storage. Old queued job keys
cannot write on completion. The shared storage accepts only SearchResultPacket
values under the new `public-discovery-packet/v2` namespace.

Discovery remains eligible only for category-free searches whose anchors already
have successful provider-catalog provenance matching the search asset class.
No extra resolver call is made. The cache adapter binds once to the exact query,
provider ID and result limit at the provider seam. The provider query builder
owns normalization; the cache preserves its exact output.
Only the direct Perplexity Search API is currently eligible. The alternate
OpenRouter search adapter also sends an environment-selected model, so it
remains uncached instead of duplicating configuration reads in the cache.

This reduces reuse and can increase latency/provider usage. Existing quota and
admission remain intact. The existing paid-work status `miss` is preserved:
the cost ledger interprets `bypass` as unpaid, so using it for an uncached paid
answer would conceal costs. Broader answer reuse needs a separate trusted
public-request/public-facts contract, without unrestricted personal prose.

## Baseline verification

- Repository lint (`ruff check src tests workflows scripts`): passed before edits.
- The broader workflow command `ruff check .` fails with **390 diagnostics in
  63 files**. Every failing file is byte-identical to the original integration.
  No exception or unrelated lint-policy change is applied; this gate remains
  failed even when CI's narrower lint command passes.
- Initial research suite: 842 passed, 17 failed from the local SciPy `_spropack`
  binary loader error. These were environment failures, not a lint exception.
- Repeating the unmodified research suite with the same locked SciPy 1.15.3
  macOS 12 ARM wheel on a temporary `PYTHONPATH`: **859 passed**.
- The temporary wheel changes no tracked dependency or shared environment file.
- Model-facing prompt/config builder and logging-call AST comparison against
  the original integration confirms those calls/text remain unchanged.

Final verification, exact head, reconciliation, and review disposition belong
to the draft PR's terminal audit after review completes. This reproduction
record is not a release-readiness claim.
