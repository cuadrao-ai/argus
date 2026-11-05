"""Run one measurement case N times with the structured tier pinned to haiku."""
import json, os, sys
from pathlib import Path
ROOT = Path(os.environ["ARGUS_REPO_ROOT"]); ENV = Path(os.environ["ARGUS_ENV_FILE"])
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
os.environ["CUADRAO_STRUCTURED_MODEL"] = "anthropic/claude-haiku-4.5"
os.environ["CUADRAO_STRUCTURED_FALLBACK_MODEL"] = "anthropic/claude-haiku-4.5"
from dotenv import load_dotenv
load_dotenv(ENV, override=False)
os.environ["ARGUS_MARKET_DATA_PROVIDER_MODE"] = "live_provider"
os.environ["ARGUS_ASSET_PROVIDER_MODE"] = "live_provider"
import argus
print("argus from", argus.__file__, "structured model", os.environ["CUADRAO_STRUCTURED_MODEL"], flush=True)
from argus.domain.market_data.assets import clear_asset_cache
from tests.evals.measurement_eval_harness import load_eval_cases, run_eval_case
clear_asset_cache()
case = next(c for c in load_eval_cases() if c.id == sys.argv[2])
results = []
for attempt in range(int(sys.argv[3])):
    r = run_eval_case(case, run_prose_judge=False)
    t = r["typed_outcome"]
    cost = sum(float(x.get("usage_cost_usd") or 0.0) for x in r["route_receipts"])
    models = sorted({x.get("model") for x in r["route_receipts"] if x.get("schema_name") == "LLMInterpretationResponse"})
    results.append({"attempt": attempt + 1, "status": r["status"], "failed_checks": r["failed_checks"], "capability_verdict": t.get("capability_verdict"), "starting_capital": t.get("starting_capital"), "clarification": (t.get("clarification") or {}).get("reason_code"), "interpretation_models": models, "cost_usd": round(cost, 6), "route_receipts": r["route_receipts"]})
    print(f"attempt {attempt+1}: {r['status']} verdict={t.get('capability_verdict')} seed={t.get('starting_capital')} clarification={(t.get('clarification') or {}).get('reason_code')} models={models} cost=${cost:.4f} checks={r['failed_checks'][:3]}", flush=True)
Path(sys.argv[1]).write_text(json.dumps(results, indent=2, default=str))
print("TOTAL", round(sum(x["cost_usd"] for x in results), 4), flush=True)
