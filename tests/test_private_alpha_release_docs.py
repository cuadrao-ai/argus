from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.evals.measurement_eval_scorecard import (
    measurement_fixture_identity_at_git_sha,
)
from tests.release_promotion_evidence_support import (
    assert_main_promotion_live_eval_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PROFILE_PATH = ROOT / ".github" / "private-alpha-release-profile.json"
PUBLIC_ACCOUNT_ACCESS_FLAG = "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED"
# The release profile owns this flag's value. Product truth is where prose states
# it, and every other doc may point here rather than repeat it.
CANONICAL_VALUE_DOC = "docs/PRODUCT.md"

# Records of a moment keep the claims they shipped with, because quoting a
# superseded posture is their job. Everything else under docs/, .agent/, and the
# repo root is standing guidance a reader consults for current truth, so it is
# in scope by default rather than by being listed.
_RECORD_TREES = (
    "docs/archive/",
    "docs/release-manifests/",
    "docs/release-evidence/",
    "docs/evidence/",
    "docs/reports/",
    "docs/qa/",
)
_DATED_RECORD = re.compile(r"^\d{4}-\d{2}-\d{2}-")
# Domain knowledge vendored for agents, not Argus access policy.
_UNRELATED_TREES = (".agent/skills/",)

# Closed boolean vocabularies, so a new stale sentence is caught by grammar
# rather than by matching a phrase somebody already wrote. These are read next to
# the flag name, where "on" would usually be a preposition ("on 2026-08-12") and
# "enabled"/"disabled" would usually be an Auth provider or an allowlist row.
_STATE_WORDS = {
    "true": ("true",),
    "false": ("false", "off"),
}
# A doc may describe the other value only inside a subordinate clause, so it
# scopes the behavior instead of declaring it. "unless" is deliberately absent:
# "stays false unless approved" asserts a standing value.
_SUBORDINATING = re.compile(r"\b(?:if|when|whenever|while|once)\b", re.IGNORECASE)
_BLOCK_BREAK = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|#|```|\|)")

# Prose names this policy without naming the variable, which is how four sites
# escaped the first pass. A sentence must be about the gate before its state
# words are read as a claim about the gate.
_GATE_SUBJECT = re.compile(
    r"public[-\s]?(?:account|permanent|registration|signup|login)"
    r"|permanent[-\s]?accounts?\b",
    re.IGNORECASE,
)
# Words that call the gate open or shut, keyed by the value each asserts, so the
# same reading runs whichever way the profile points. "on" and "closed" are
# absent because "on 2026-08-12" and "fails closed" are ordinary prose here.
_GATE_STATE = {
    "true": re.compile(r"\b(?:true|open|opens|opened|enabled)\b", re.IGNORECASE),
    "false": re.compile(r"\b(?:false|off|disabled)\b", re.IGNORECASE),
}
# Words that cannot be the noun a state word modifies, so a state word followed
# by one of them, by punctuation, or by nothing is predicative and asserts the
# gate: "access is disabled", "registration is enabled", "off for new accounts".
_NOT_A_MODIFIED_NOUN = (
    r"for|so|and|or|but|to|on|in|of|with|no|not|all|any|every|because|since|"
    r"unless|while|when|if|then|until|except|by|as|at|from|that|which|it|its|"
    r"this|these|those|there|here|only|merely|just|simply|still|now|today"
)
# Attributive instead: the word modifies the noun after it and describes that
# noun, not the gate. "an explicitly disabled allowlist row" stays true while the
# gate is open, and "every enabled permanent Auth provider" is not a gate claim
# either, which is why both boolean words are safe to read in both directions.
# Asking what the word modifies replaces enumerating the nouns it might modify.
_ATTRIBUTIVE = re.compile(
    rf"[\s-]+(?!(?:{_NOT_A_MODIFIED_NOUN})\b)\w+",
    re.IGNORECASE,
)
# What precedes settles it before what follows has to. A copula makes the word
# predicative whatever comes next, so "is disabled pending review" is a gate
# claim even though "pending" could pass for the noun it modifies. A determiner
# after the copula means the opposite, as in "is a disabled row", so it is
# excluded rather than read as a claim.
_PREDICATIVE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|remains?|stays?|becomes?|became|"
    r"fails?|defaults?|keeps?|kept)\s+"
    r"(?!(?:a|an|the)\b)(?:\w+\s+)?$",
    re.IGNORECASE,
)
# "not open" asserts the other state, however far the negator sits from it, so
# this looks anywhere earlier in the same clause rather than counting words.
# "not only open" asserts this state, so the additive and emphatic forms are
# excluded rather than read as negation.
_NEGATION = re.compile(
    r"\b(?:not|never|no longer|cannot|without)\b(?!\s+(?:only|merely|just|simply)\b)",
    re.IGNORECASE,
)
# One clause is the unit a claim lives in. Splitting here lets a state word be
# read whether it sits before or after the account phrase, while keeping a
# neighbouring flag's value or an unrelated subject out of this claim.
_CLAUSE_BREAK = re.compile(
    r",\s+|;\s+|:\s+|\s+(?:and|but|or|so|because|although|though|whereas)\s+",
    re.IGNORECASE,
)
# Another environment variable ends this flag's value: a stale value after one of
# these belongs to that variable, not to ours.
_OTHER_ENV_VAR = re.compile(r"\b(?:ARGUS|NEXT_PUBLIC|SUPABASE|OPENROUTER|ALPACA)_\w+")
# Self-identifying: this term means the gate is shut, whatever the subject.
_GATE_SHUT_TERM = "allowlist-gated"

KNOWN_MAIN_PROMOTION_MANIFESTS_WITHOUT_LIVE_EVAL = frozenset(
    {
        "2026-06-18-private-alpha-next-ci-cd-sota.md",
        "2026-06-27-private-alpha-p2-checkpoint.md",
        "2026-07-14-main-production-promotion.md",
        "2026-07-10-private-alpha-next-interpret-surface.md",
        "2026-08-05-main-production-promotion.md",
        "2026-08-11-main-production-promotion.md",
        "2026-08-12-main-production-promotion-716221f.md",
        "2026-08-12-main-production-promotion.md",
    }
)


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _release_profile_value(key: str) -> str:
    profile = json.loads(RELEASE_PROFILE_PATH.read_text(encoding="utf-8"))
    return profile["services"]["api"]["env"][key]


def _standing_doc_paths() -> list[Path]:
    """Every Markdown file whose claims are supposed to be true right now."""
    candidates = sorted(
        {
            *(ROOT / "docs").rglob("*.md"),
            *ROOT.glob("*.md"),
            *(ROOT / ".agent").rglob("*.md"),
        }
    )
    return [
        path
        for path in candidates
        if not path.relative_to(ROOT)
        .as_posix()
        .startswith(_RECORD_TREES + _UNRELATED_TREES)
        and not _DATED_RECORD.match(path.name)
    ]


def _claim_sentences(text: str) -> Iterator[str]:
    """Yield sentences with Markdown wrapping collapsed.

    Blocks break on blank lines, list markers, headings, fences, and table rows
    so a claim is never read across two unrelated bullets. A fenced block yields
    one line at a time, because its lines are already separate statements and
    joining them would read a neighbouring variable's value as this one's.
    """
    block: list[str] = []
    fenced = False
    for line in text.splitlines() + [""]:
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            if line.strip():
                yield line.strip()
            continue
        if not line.strip() or _BLOCK_BREAK.match(line):
            if block:
                yield from re.split(r"(?<=[.;])\s+", " ".join(" ".join(block).split()))
                block = []
            if line.strip():
                block = [line]
            continue
        block.append(line)


def _declares(position: int | None, scope_at: int | None) -> bool:
    """Whether a value at `position` states the gate's standing posture.

    A subordinating conjunction opening before it scopes the value to a case
    instead, which is how a doc keeps describing the off state honestly.
    """
    return position is not None and not (scope_at is not None and scope_at < position)


def _clauses(sentence: str) -> Iterator[tuple[int, str]]:
    """Yield (offset, clause) for each clause of `sentence`."""
    start = 0
    for gap in _CLAUSE_BREAK.finditer(sentence):
        if gap.start() > start:
            yield start, sentence[start : gap.start()]
        start = gap.end()
    if start < len(sentence):
        yield start, sentence[start:]


def _flag_value_claim(clause: str, stale_words: tuple[str, ...]) -> int | None:
    """Where the clause gives this flag the stale value, if it does.

    Only text after the flag name counts, and another environment variable ends
    the window, so a neighbouring flag's value is never read as this one's.
    """
    named = clause.find(PUBLIC_ACCOUNT_ACCESS_FLAG.lower())
    if named < 0:
        return None
    window_end = len(clause)
    if other := _OTHER_ENV_VAR.search(clause, named + len(PUBLIC_ACCOUNT_ACCESS_FLAG)):
        window_end = other.start()
    return min(
        (
            match.start()
            for word in stale_words
            if (match := re.compile(rf"\b{word}\b").search(clause, named, window_end))
        ),
        default=None,
    )


def _gate_state_claim(clause: str, stale_state: re.Pattern[str]) -> int | None:
    """Where the clause asserts the stale gate state in words, if it does.

    The clause must be about the gate, in either word order, then each state word
    is judged by how it is used: a copula before it makes it predicative and a
    claim about the gate, while modifying the noun after it describes that noun.
    """
    if not _GATE_SUBJECT.search(clause):
        return None
    for match in stale_state.finditer(clause):
        before = clause[: match.start()]
        if _NEGATION.search(before):
            continue
        if _PREDICATIVE.search(before):
            return match.start()
        if _ATTRIBUTIVE.match(clause, match.end()):
            continue
        return match.start()
    return None


def _access_claim_contradictions(text: str, declared: str) -> list[str]:
    """Claims in `text` that a reader would take as the wrong flag value.

    Clauses are read whether or not they name the variable, because prose that
    describes the policy in words is how most of this drift survived.
    """
    stale = "false" if declared == "true" else "true"
    stale_words = _STATE_WORDS[stale]
    stale_state = _GATE_STATE[stale]

    found: list[str] = []
    for sentence in _claim_sentences(text):
        lowered = sentence.lower()

        # The named flag keeps its value across a whole sentence, because "remains
        # a separate policy and stays `false`" carries the subject over the
        # conjunction. Binding the value to the name is what keeps a neighbouring
        # flag out, so this needs no clause split.
        sentence_scope = _SUBORDINATING.search(lowered)
        if _declares(
            _flag_value_claim(lowered, stale_words),
            sentence_scope.start() if sentence_scope else None,
        ):
            found.append(sentence)
            continue

        # Prose is read one clause at a time instead, so a state word counts
        # whether it sits before or after the account phrase, and an unrelated
        # subject in a neighbouring clause is not dragged in.
        for offset, clause in _clauses(lowered):
            # A subordinating conjunction earlier in the sentence scopes this
            # clause too, so splitting cannot strip an off-case description of
            # the condition that made it honest.
            inherited = _SUBORDINATING.search(lowered[:offset])
            local = _SUBORDINATING.search(clause)
            scope_at = -1 if inherited else (local.start() if local else None)

            # Runs in both directions: after a rollback to `false`, prose still
            # calling registration open is the same defect mirrored.
            if declared == "true" and _GATE_SHUT_TERM in clause:
                claimed = clause.index(_GATE_SHUT_TERM)
            else:
                claimed = _gate_state_claim(clause, stale_state)

            if _declares(claimed, scope_at):
                found.append(sentence)
                break
    return found


def test_public_account_access_claim_detector_reads_grammar_not_phrases() -> None:
    """The guard above is only worth its name if these shapes stay separated."""
    must_catch = (
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}=false`",
        f"The independent `{PUBLIC_ACCOUNT_ACCESS_FLAG}` policy remains false.",
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}` defaults off and controls accounts.",
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}` stays false unless the founder agrees.",
        # The named flag keeps its value across a conjunction, so reading prose
        # clause by clause must not sever the value from the name.
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}` remains a separate policy and stays "
        "`false` until explicitly approved.",
        "Public account creation is still allowlist-gated.",
        "Standing mitigations: allowlist-gated account creation, and Turnstile.",
        # Shapes that never name the variable, which is how four sites survived
        # the first pass: DESIGN.md and private-alpha-next-integration.md.
        "Public account access remains explicitly disabled and founder owned.",
        "Guest defaults on with rollback; public-account access remains off.",
        "Rollback is flags first: keep public-account access false.",
        "Public permanent accounts are disabled, so guest chrome hides signup.",
        # A denial noun after the state word does not make it the exception when a
        # function word or punctuation separates them: these shut the gate and
        # then mention accounts, rather than describing one denied account.
        "Public account access is disabled for all accounts.",
        "Public registration is off for new accounts.",
        "Public signup is disabled, so no accounts can be created.",
        "Public signup is disabled for new accounts.",
        # A copula settles it before the following word can pose as the noun
        # being modified.
        "Public signup is disabled pending review.",
        "Public account access is off limits.",
        "Public account creation is disabled indefinitely.",
        # The state word may sit before the account phrase, not only after it.
        "Registration is disabled for public accounts.",
        # A fenced block declares one value per line.
        f"```bash\nOTHER_FLAG=true\n{PUBLIC_ACCOUNT_ACCESS_FLAG}=false\n```",
    )
    must_allow = (
        f"When `{PUBLIC_ACCOUNT_ACCESS_FLAG}` is off, signup is allowlist-gated.",
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}=true` has been live since 2026-08-12.",
        # Conditional and procedural off-state guidance stays writable, which is
        # why the assignment is parsed rather than banned as a substring.
        f"When `{PUBLIC_ACCOUNT_ACCESS_FLAG}=false`, only allowlisted roles enter.",
        f"When rolling back, set `{PUBLIC_ACCOUNT_ACCESS_FLAG}=false` and redeploy.",
        # A disabled allowlist row is not a claim that the gate is shut.
        "Public registration is open. The server turns away only an email "
        "carrying an explicitly disabled allowlist row.",
        "Public-account access is an independent gate that fails closed when "
        "unset, so a deployment omitting the variable denies registration.",
        # A neighbouring variable's `false` is not this gate's value.
        f"```bash\n{PUBLIC_ACCOUNT_ACCESS_FLAG}=true\nOTHER_FLAG=false\n```",
        # Accurate prose may keep the denial exception next to the subject. A
        # distance rule rejected these and forced authors to pad sentences.
        "Public signup is open except for explicitly disabled emails.",
        "Public account creation is open, and only an explicitly disabled row "
        "is refused.",
        "Public registration is open, so a disabled allowlist entry is the only "
        "refusal.",
        # Negation asserts the open state, so it is not a shut claim.
        "Public account creation is not disabled.",
        # A determiner after the copula means the word modifies the noun after
        # it, so this is one denied account rather than the gate.
        "Public registration is open, so the only refusal is a disabled "
        "allowlist entry.",
        # A neighbouring flag's value is not this flag's, even in one sentence.
        f"Set `ARGUS_GUEST_ACCESS_ENABLED=false` but keep "
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}=true`.",
        # Negation holds however far it sits from the state word.
        "Public signup is not expected to be open.",
        "Public registration is not currently expected to remain open.",
        # The founder-owned precondition in API_CONTRACT.md must never read as a
        # stale claim, or a later round deletes it to get the suite green.
        "Before that flag may be enabled, founder-approved evidence must prove "
        "that every enabled permanent Auth provider supplies a verified email "
        "compatible with profile and allowlist-role rules.",
        "Only an explicitly disabled allowlist row blocks signup or login.",
    )

    for claim in must_catch:
        assert _access_claim_contradictions(claim, "true"), f"missed: {claim}"
    for claim in must_allow:
        assert not _access_claim_contradictions(claim, "true"), f"false alarm: {claim}"

    # The guard inverts with the profile rather than hardcoding today's posture.
    # A rollback to `false` has to catch open-state prose the same way, or the
    # docs only derive from the profile in one direction.
    for claim in (
        f"`{PUBLIC_ACCOUNT_ACCESS_FLAG}=true` is live.",
        "Public registration is now open.",
        "Public account creation is open to anyone.",
        "Permanent accounts opened to the public.",
        # A synonym list could not carry these; asking what the word modifies can.
        "Public registration is enabled.",
        "Public account access is enabled for everyone.",
        "Public signup is open for new accounts.",
        # Additive "not only" asserts the state rather than negating it.
        "Public signup is not only open; it is unrestricted.",
        # Mirror of the before-the-phrase case in the rollback direction.
        "Registration remains open for public accounts.",
    ):
        assert _access_claim_contradictions(
            claim, "false"
        ), f"missed on rollback: {claim}"
    for claim in (
        "Public account creation is still allowlist-gated.",
        "Public registration is not open.",
        f"When `{PUBLIC_ACCOUNT_ACCESS_FLAG}=true`, any undisabled email may enter.",
    ):
        assert not _access_claim_contradictions(claim, "false"), f"false alarm: {claim}"


def test_public_account_access_claims_cannot_contradict_the_release_profile() -> None:
    """The release profile owns this flag; standing prose only derives from it.

    Prose drifted out of agreement with the deployed flag once already, because
    nothing connected a sentence to the profile that decides the value.
    """
    declared = _release_profile_value(PUBLIC_ACCOUNT_ACCESS_FLAG)
    assert declared in _STATE_WORDS, (
        f"{PUBLIC_ACCOUNT_ACCESS_FLAG} is `{declared}` in the release profile. "
        "Add its boolean spelling to _STATE_WORDS before this guard can read it."
    )
    declared_assignment = f"{PUBLIC_ACCOUNT_ACCESS_FLAG}={declared}"

    contradictions: list[str] = []
    for path in _standing_doc_paths():
        relative = path.relative_to(ROOT).as_posix()
        contradictions.extend(
            f"{relative}: {claim}"
            for claim in _access_claim_contradictions(
                path.read_text(encoding="utf-8"), declared
            )
        )

    assert not contradictions, (
        f"{PUBLIC_ACCOUNT_ACCESS_FLAG} is `{declared}` in "
        f"{RELEASE_PROFILE_PATH.name}, so these standing claims are wrong:\n"
        + "\n".join(f"  - {item}" for item in contradictions)
    )
    # One doc states the value; the rest may point at it. Requiring the literal
    # in every doc that mentions the flag was asking a test to keep copies in
    # agreement, which is the split-brain shape this repo forbids, and it made a
    # flag change a hand-edit of every copy.
    assert declared_assignment in _source(CANONICAL_VALUE_DOC), (
        f"{CANONICAL_VALUE_DOC} is where prose states this flag's value, so it "
        f"must say `{declared_assignment}` to match {RELEASE_PROFILE_PATH.name}."
    )
def _commit_measurement_fixture_candidate(
    repository_root: Path,
    *,
    case_ids: tuple[str, ...],
) -> str:
    fixture_dir = repository_root / "tests" / "evals" / "measurement_cases"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "messy_english.yaml").write_text(
        json.dumps(
            {
                "category": "messy_english",
                "cases": [{"id": case_id} for case_id in case_ids],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "tests/evals/measurement_cases"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Argus Eval Test",
            "-c",
            "user.email=argus-eval@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "test fixture candidate",
        ],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_main_promotion_manifest_without_live_eval_scorecard_is_rejected(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "2026-08-13-main-production-promotion.md"
    manifest_path.write_text(
        "# Main Production Promotion Manifest\n\n"
        f"- Candidate SHA: `{'a' * 40}`\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="missing durable live eval scorecard"):
        assert_main_promotion_live_eval_evidence(manifest_path)


def test_main_promotion_manifest_accepts_matching_clean_live_scorecard(
    tmp_path: Path,
) -> None:
    candidate_sha = _commit_measurement_fixture_candidate(
        tmp_path,
        case_ids=("case-a", "case-b"),
    )
    fixture_identity = measurement_fixture_identity_at_git_sha(
        candidate_sha=candidate_sha,
        repository_root=tmp_path,
    )
    scorecard_relative_path = (
        "docs/reports/evidence/promotion/argus-eval-scorecard.json"
    )
    scorecard_path = tmp_path / scorecard_relative_path
    scorecard_path.parent.mkdir(parents=True)
    scorecard_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "provenance": {
                    "evaluation_mode": "live",
                    "market_data_provider_mode": "live_provider",
                    "asset_provider_mode": "live_provider",
                    "candidate_sha": candidate_sha,
                    "python_version": "3.10.20",
                    "fixture_sha256": fixture_identity.sha256,
                    "fixture_case_ids": list(fixture_identity.case_ids),
                    "worktree_clean": True,
                    "live_market_data_probe": {
                        "requested_date_range": {
                            "start": "2024-01-01",
                            "end": "2024-01-10",
                        },
                        "effective_date_range": {
                            "start": "2024-01-02",
                            "end": "2024-01-10",
                        },
                        "adjustment_reason": "calendar_alignment",
                    },
                },
                "totals": {
                    "passed": 2,
                    "failed": 0,
                    "expected_failed": 0,
                    "unexpected_pass": 0,
                    "skipped": 0,
                },
                "results": [
                    {
                        "id": "case-a",
                        "category": "messy_english",
                        "status": "passed",
                    },
                    {
                        "id": "case-b",
                        "category": "messy_spanish",
                        "status": "passed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "2026-08-13-main-production-promotion.md"
    manifest_path.write_text(
        "# Main Production Promotion Manifest\n\n"
        f"- Candidate SHA: `{candidate_sha}`\n"
        f"- Live eval scorecard: `{scorecard_relative_path}`\n",
        encoding="utf-8",
    )

    assert_main_promotion_live_eval_evidence(
        manifest_path,
        repository_root=tmp_path,
    )

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    scorecard["totals"]["passed"] = 1
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")
    with pytest.raises(AssertionError, match="totals do not match"):
        assert_main_promotion_live_eval_evidence(
            manifest_path,
            repository_root=tmp_path,
        )


def test_main_promotion_manifest_rejects_summary_without_complete_results(
    tmp_path: Path,
) -> None:
    candidate_sha = _commit_measurement_fixture_candidate(
        tmp_path,
        case_ids=("case-a", "case-b"),
    )
    scorecard_relative_path = (
        "docs/reports/evidence/promotion/argus-eval-scorecard.json"
    )
    scorecard_path = tmp_path / scorecard_relative_path
    scorecard_path.parent.mkdir(parents=True)
    scorecard_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "provenance": {
                    "evaluation_mode": "live",
                    "market_data_provider_mode": "live_provider",
                    "asset_provider_mode": "live_provider",
                    "candidate_sha": candidate_sha,
                    "python_version": "3.10.20",
                    "fixture_sha256": "b" * 64,
                    "fixture_case_ids": ["case-a"],
                    "worktree_clean": True,
                    "live_market_data_probe": {
                        "requested_date_range": {
                            "start": "2024-01-01",
                            "end": "2024-01-10",
                        },
                        "effective_date_range": {
                            "start": "2024-01-02",
                            "end": "2024-01-10",
                        },
                        "adjustment_reason": "calendar_alignment",
                    },
                },
                "totals": {
                    "passed": 1,
                    "failed": 0,
                    "expected_failed": 0,
                    "unexpected_pass": 0,
                    "skipped": 0,
                },
                "results": [
                    {
                        "id": "case-a",
                        "category": "messy_english",
                        "status": "passed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "2026-08-13-main-production-promotion.md"
    manifest_path.write_text(
        "# Main Production Promotion Manifest\n\n"
        f"- Candidate SHA: `{candidate_sha}`\n"
        f"- Live eval scorecard: `{scorecard_relative_path}`\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="candidate fixture identity"):
        assert_main_promotion_live_eval_evidence(
            manifest_path,
            repository_root=tmp_path,
        )


def test_main_promotion_manifests_require_live_eval_scorecard_evidence() -> None:
    manifest_dir = ROOT / "docs" / "release-manifests"
    manifests = []
    for manifest_path in sorted(manifest_dir.glob("*.md")):
        if manifest_path.name == "TEMPLATE.md":
            continue
        manifest = manifest_path.read_text(encoding="utf-8")
        if (
            "main-production-promotion" in manifest_path.name
            or re.search(r"^- Promotion target: `?main`?$", manifest, re.M)
        ):
            manifests.append(manifest_path)
    missing_evidence: set[str] = set()
    for manifest_path in manifests:
        try:
            assert_main_promotion_live_eval_evidence(manifest_path)
        except AssertionError as exc:
            if "missing durable live eval scorecard" not in str(exc):
                raise
            missing_evidence.add(manifest_path.name)

    assert missing_evidence == KNOWN_MAIN_PROMOTION_MANIFESTS_WITHOUT_LIVE_EVAL


def test_private_launch_runbook_documents_ci_cd_release_gate() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")

    assert "docs/specs/private-alpha-ci-cd-sota.md" in runbook
    assert "docs/specs/private-alpha-next-decision-memo.md" in runbook
    assert "later-context document, not part of this release gate" in runbook
    assert ".github/local-smoke.sh --expected-sha" in runbook
    assert 'ARGUS_CANARY_SHA="$(git rev-parse HEAD)"' in runbook
    assert (
        "ARGUS_CANARY_EVIDENCE_PATH=temp/release-evidence/release-coherence.json"
        in runbook
    )
    assert (
        "ARGUS_CANARY_CAPTURE_PATH=temp/release-evidence/authenticated-browser-capture.json"
        in runbook
    )
    assert "scripts/ops/canary_capture_replay.py" in runbook
    assert "Do not rerun the charged journey to collect a capture" in runbook
    assert "Docker is optional" in runbook
    assert "private-alpha-release-coherence-evidence" in runbook
    assert "private-alpha-authenticated-browser-evidence" in runbook
    assert "both authoritative canary surfaces" in runbook
    assert "docs/release-manifests/TEMPLATE.md" in runbook
    assert "release manifest" in runbook
    assert "rollback target" in runbook
    assert "api_web_env_fingerprint" in runbook
    assert "workflow_env_fingerprint" in runbook
    assert "workflow_env_status" in runbook
    assert "workflow_runtime_provider_mode=live_provider" in runbook
    assert "workflow_runtime_proof=ready" in runbook
    assert "never\n  visits the signup or login page" in runbook
    assert "Canary identity, session rotation, and revocation" in runbook
    assert "workflow-service proof" in runbook
    assert "approver" in runbook


def test_production_migration_gate_is_executable_and_precedes_service_deploy() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    release_contract = _source("docs/specs/private-alpha-ci-cd-sota.md")
    manifest = _source("docs/release-manifests/TEMPLATE.md")
    command = "scripts/ops/production_migration_gate.py"

    promotion_path = release_contract.split("### Promotion Path", 1)[1].split(
        "## Implementation Phases",
        1,
    )[0]
    tester_gate = runbook.split("## Before Tester Sessions", 1)[1].split(
        "## Backtest Workflow Modes",
        1,
    )[0]

    for source in (promotion_path, tester_gate):
        normalized = " ".join(source.split())
        assert command in source
        assert "ARGUS_PRODUCTION_DATABASE_URL" in source
        assert "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT" in source
        assert "status=pass" in source
        assert "never applies migrations" in normalized
        assert "human" in normalized.lower()
        assert "statement" in normalized.lower()
        assert "content drift" in normalized.lower()
        assert "query" in normalized.lower()
        assert "verify-full" in normalized.lower()

    promotion_gate_index = promotion_path.index(command)
    promotion_candidate_index = promotion_path.index(
        "exact would-be `main` promotion commit"
    )
    promotion_landing_index = promotion_path.index("Land only the gated candidate")
    promotion_landed_gate_index = promotion_path.index("--verify-landed-ref origin/main")
    assert promotion_candidate_index < promotion_gate_index
    assert promotion_gate_index < promotion_landing_index
    assert promotion_landing_index < promotion_landed_gate_index
    assert promotion_landed_gate_index < promotion_path.index(
        "Update the release/config contract"
    )
    assert promotion_landed_gate_index < promotion_path.index(
        "Promote the live environment"
    )
    assert promotion_gate_index < promotion_path.index(
        "Update the release/config contract"
    )
    assert promotion_gate_index < promotion_path.index("Promote the live environment")
    assert "landed `origin/main` SHA differs" in promotion_path
    assert "rerun the gate against that landed SHA" in " ".join(promotion_path.split())
    runbook_gate_index = tester_gate.index(command)
    runbook_landing_index = tester_gate.index("Land or read back the candidate")
    runbook_landed_gate_index = tester_gate.index("--verify-landed-ref origin/main")
    assert "exact would-be `main` promotion commit" in tester_gate
    assert runbook_gate_index < runbook_landing_index
    assert runbook_landing_index < runbook_landed_gate_index
    assert runbook_landed_gate_index < tester_gate.index("sync the Blueprint")
    assert runbook_landed_gate_index < tester_gate.index("api-real-workflow-on")
    assert runbook_landed_gate_index < tester_gate.index(
        "Deploy **all three live services**"
    )
    assert runbook_gate_index < tester_gate.index("sync the Blueprint")
    assert runbook_gate_index < tester_gate.index("api-real-workflow-on")
    assert runbook_gate_index < tester_gate.index("Deploy **all three live services**")
    assert "rerun the gate against the landed SHA" in " ".join(tester_gate.split())
    assert "Production Migration Gate" in manifest
    assert "Candidate migrations" in manifest
    assert "Applied production migrations" in manifest
    assert "Missing migrations" in manifest
    assert "Migration content drift" in manifest
    assert "statement-array SHA-256" in manifest
    assert "Safety classifications" in manifest
    assert "Landed `origin/main` SHA" in manifest
    assert "Gate-to-landed-SHA identity" in manifest


def test_public_alpha_waitlist_rollback_floor_is_durable_and_ordered() -> None:
    evidence = _source("docs/release-evidence/public-alpha-readiness.md")
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    evidence_text = " ".join(evidence.split())
    runbook_text = " ".join(runbook.split())

    assert "061ba50e" in evidence_text
    assert "prefer a forward fix" in evidence_text.lower()
    assert "out-of-band Render control-plane readback" in evidence_text
    assert "serviceDetails.maintenanceMode.enabled=true" in evidence_text
    assert "https://api.arguschat.ai/api/v1/auth/access-requests" in evidence_text
    assert "every configured custom API domain" in evidence_text
    assert "exact HTTP `503` maintenance-mode status" in evidence_text
    assert "configured maintenance page marker or SHA-256 fingerprint" in evidence_text
    assert "An arbitrary `403`, `429`, or `503` is not maintenance proof." in (
        evidence_text
    )
    assert (
        "`https://argus-ohr5.onrender.com` must return HTTP `404` and is not a "
        "maintenance probe surface" in evidence_text
    )
    assert (
        "do not require `503` from that hostname" in evidence_text
    )
    assert "must not return HTTP `202`" not in evidence_text
    assert (
        "If the control-plane state or expected response signature cannot be "
        "verified, stop and forward-fix." in evidence_text
    )
    assert "same-SHA Render service restart" in evidence_text
    assert "restart deploy is terminal with `status=live`" in evidence_text
    assert "non-empty `finishedAt`" in evidence_text
    assert "pre-restart instance IDs" in evidence_text
    assert "old-instance shutdown/drain is complete" in evidence_text
    assert "no pre-maintenance API worker remains" in evidence_text
    assert "The table lock does not drain a worker paused before its insert." in (
        evidence_text
    )
    assert (
        "lock table public.private_alpha_allowlist in access exclusive mode;"
        in evidence_text.lower()
    )
    assert "pre-block in-flight inserts" in evidence_text
    assert "role = 'requested'" in evidence_text
    assert "disabled_at is null" in evidence_text
    assert "active_requested_rows" in evidence_text
    assert "keep maintenance enabled" in evidence_text
    assert "exact rollback SHA is live in Render deploy metadata" in evidence_text
    assert "private network, SSH, or local loopback" in evidence_text
    assert "non-mutating invalid-body probe" in evidence_text
    assert "require HTTP `404` route absence" in evidence_text
    assert "A present route, including HTTP `422`" in evidence_text
    assert "If no private verification surface is available" in evidence_text
    assert "re-read the maintenance configuration and response signature" in (
        evidence_text
    )
    assert "Disable maintenance last" in evidence_text
    assert "public invalid-body readback" in evidence_text
    assert (
        "that hostname remains excluded from the maintenance fingerprint surface"
        in evidence_text
    )
    assert (
        "is not an application route-absence probe surface" in evidence_text
    )
    assert "Do not execute this SQL as part of repository verification." in evidence_text
    for official_reference in (
        "https://render.com/docs/maintenance-mode",
        "https://render.com/docs/deploys#zero-downtime-deploys",
        "https://api-docs.render.com/reference/restart-service",
        "https://api-docs.render.com/reference/list-instances",
    ):
        assert official_reference in evidence_text

    maintenance_index = evidence_text.index("out-of-band Render control-plane readback")
    signature_index = evidence_text.index(
        "configured maintenance page marker or SHA-256 fingerprint"
    )
    restart_index = evidence_text.index("same-SHA Render service restart")
    restart_live_index = evidence_text.index(
        "restart deploy is terminal with `status=live`"
    )
    old_shutdown_index = evidence_text.index("old-instance shutdown/drain is complete")
    lock_index = evidence_text.lower().index(
        "lock table public.private_alpha_allowlist in access exclusive mode;"
    )
    disable_index = evidence_text.index("update public.private_alpha_allowlist")
    readback_index = evidence_text.index("select count(*) as active_requested_rows")
    commit_index = evidence_text.index("commit;")
    rollback_index = evidence_text.index("deploy the rollback")
    exact_sha_index = evidence_text.index(
        "exact rollback SHA is live in Render deploy metadata"
    )
    private_probe_index = evidence_text.index("non-mutating invalid-body probe")
    maintenance_reread_index = evidence_text.index(
        "re-read the maintenance configuration and response signature"
    )
    disable_maintenance_index = evidence_text.index("Disable maintenance last")
    public_readback_index = evidence_text.index("public invalid-body readback")
    assert (
        maintenance_index
        < signature_index
        < restart_index
        < restart_live_index
        < old_shutdown_index
        < lock_index
        < disable_index
        < readback_index
        < commit_index
        < rollback_index
        < exact_sha_index
        < private_probe_index
        < maintenance_reread_index
        < disable_maintenance_index
        < public_readback_index
    )

    assert "release-evidence/public-alpha-readiness.md" in runbook_text
    assert "061ba50e" in runbook_text
    assert "serviceDetails.maintenanceMode.enabled=true" in runbook_text
    assert "exact maintenance status and page fingerprint" in runbook_text
    assert "`argus-app` onrender URL" in runbook_text
    assert "https://argus-ohr5.onrender.com` must return HTTP `404`" in runbook_text
    assert "Never front the API with a Cloudflare Worker" in runbook_text
    assert "same-SHA restart" in runbook_text
    assert "old-instance shutdown/drain" in runbook_text
    assert "ACCESS EXCLUSIVE" in runbook_text
    assert "private invalid-body route-absence probe" in runbook_text
    assert "exact rollback SHA" in runbook_text
    assert "disable maintenance last" in runbook_text
    assert "HTTP `202`" not in runbook_text.split("### Waitlist rollback floor", 1)[1]


def test_waitlist_exposure_waits_for_paid_render_rollback_controls() -> None:
    evidence = " ".join(
        _source("docs/release-evidence/public-alpha-readiness.md").split()
    )
    runbook = " ".join(_source("docs/PRIVATE_LAUNCH_RUNBOOK.md").split())
    blueprint = _source("render.yaml")
    api_service = blueprint.split("name: argus-api", 1)[1].split("\n  - type:", 1)[0]
    app_service = blueprint.split("name: argus-app", 1)[1]

    assert "plan: standard" in api_service
    assert "plan: starter" in app_service
    assert (
        "The checked-in Render Blueprint declares `argus-api` as `plan: standard` "
        "and `argus-app` as `plan: starter`." in evidence
    )
    assert (
        "Do not apply "
        "`supabase/migrations/20260731080154_add_requested_private_alpha_access.sql` "
        "or accept access-request traffic until the paid-control readbacks below "
        "are complete." in evidence
    )
    assert "read back a paid API instance type from Render's control plane" in evidence
    assert "`serviceDetails.plan != free`" in evidence
    assert "prove maintenance mode is available and can be enabled" in evidence
    assert "private-network, SSH, or local-loopback verification capability" in evidence
    assert (
        "If any paid capability is absent, stop: do not apply the migration and "
        "do not expose the route." in evidence
    )
    assert (
        "Only after every paid-control check passes may the requested-role "
        "migration be applied and access-request traffic be exposed." in evidence
    )
    for official_reference in (
        "https://render.com/docs/free",
        "https://render.com/docs/private-network",
        "https://render.com/docs/ssh",
    ):
        assert official_reference in evidence

    paid_plan_index = evidence.index(
        "read back a paid API instance type from Render's control plane"
    )
    maintenance_index = evidence.index(
        "prove maintenance mode is available and can be enabled"
    )
    private_surface_index = evidence.index(
        "private-network, SSH, or local-loopback verification capability"
    )
    exposure_index = evidence.index(
        "Only after every paid-control check passes may the requested-role migration"
    )
    assert paid_plan_index < maintenance_index < private_surface_index < exposure_index

    assert "The live `argus-api` plan is `standard`" in runbook
    assert "The live `argus-app` plan is `starter`" in runbook
    assert "requested-role migration and access-request exposure are complete" in runbook
    assert "paid API instance type" in runbook
    assert "maintenance and private/SSH/local verification controls" in runbook
    assert "rollback below `061ba50e` remains forbidden" in runbook


def test_public_alpha_hosted_release_proof_is_durable() -> None:
    evidence = " ".join(
        _source("docs/release-evidence/public-alpha-readiness.md").split()
    )
    approval_delivery = _source(
        "docs/release-evidence/artifacts/public-alpha-approval-email-delivery.json"
    )

    for expected in (
        "`2330ec42d52d912b6cdb1be5e74aa343a5d5abe0`",
        "`dep-d9miovnqj5pc73d3utrg`",
        "`dep-d9miovnavr4c73eg6agg`",
        "`wfv-d9miovjm8hqs73cebpeg`",
        "API CPU limit: `1 CPU`",
        "API memory limit: `2,147,483,600 bytes`",
        "app CPU limit: `0.5 CPU`",
        "app memory limit: `536,870,900 bytes`",
        "`maintenanceMode.enabled=true`",
        "`af51f998b76af7e25f45b40bc730c0acd965285ecb9a427655fdecb7193f365d`",
        "`private_health_final_sha status=200`",
        "`job-d9miqe3m8hqs73cee9h0`",
        "`917772c9a654727c8f69720bd3b591b02156ed2bcc979c4b758866928810897e`",
        "`access_request_probe status=202 accepted=true`",
        "`job-d9mic0navr4c73efapb0`",
        "`14c92439-e50f-4e3f-846c-228196808349`",
        "`approval_email_probe status=200`",
        "`job-d9midlfavr4c73efe2pg`",
        "`https://argus-app-suz5.onrender.com/?auth=signup`",
        "`maintenanceMode.enabled=false`",
        "`311fc3f1eed2fa039ba185510cc96adcbfabd1d89d3c6ac13a57a16dd1ae0b41`",
        "hosted-en-desktop-request-access.png",
        "hosted-en-desktop-request-accepted.png",
        "hosted-es-419-desktop-request-access.png",
        "hosted-es-419-desktop-request-accepted.png",
        "en-desktop-check-email.png",
        "en-mobile-check-email.png",
        "es-419-desktop-check-email.png",
        "es-419-mobile-check-email.png",
        "zero browser console errors and zero warnings",
        "zero temporary allowlist rows",
        "zero temporary Auth users",
    ):
        assert expected in evidence

    for expected in (
        '"id": "14c92439-e50f-4e3f-846c-228196808349"',
        '"status": "delivered"',
        '"to": "delivered@resend.dev"',
        '"signup_url": "https://argus-app-suz5.onrender.com/?auth=signup"',
    ):
        assert expected in approval_delivery


def test_public_alpha_load_and_cost_evidence_is_durable() -> None:
    evidence = " ".join(
        _source("docs/release-evidence/public-alpha-readiness.md").split()
    )

    assert "17098b8173d845aa5033036244a71cdcc3283ddb" in evidence
    assert "1 running / 0 queued" in evidence
    assert "5 running / 0 queued" in evidence
    assert "1 running / 2 queued" in evidence
    assert "5 running / 10 queued" in evidence
    assert "invalid_job_contract" in evidence
    assert "failed_upstream" in evidence
    assert "26 task runs" in evidence
    assert "28 attempts" in evidence
    assert "1,466 seconds" in evidence
    assert "0.407222 hours" in evidence
    assert "$0.081444" in evidence
    assert "0.15 CPU" in evidence
    assert "83.88%" in evidence
    assert "$32/month fixed service floor" in evidence
    assert "$25 API + $7 app" in evidence
    assert "Standard Workflow compute" in evidence
    assert "$0.20/hour" in evidence


def test_guest_launch_safety_records_live_hard_provider_caps() -> None:
    safety = " ".join(_source("docs/GUEST_PUBLIC_LAUNCH_SAFETY.md").split())

    assert "There is no hard provider spending limit." not in safety
    assert "registered key is not capped at `$10/week`" in safety
    assert "Guest key is not capped at `$5/week`" in safety


def test_public_alpha_spec_drops_superseded_inference_footer() -> None:
    spec = _source("docs/superpowers/specs/2026-07-30-public-alpha-readiness.md")

    assert "### Inference" not in spec
    assert "exact exit-criterion number" not in spec
    assert 'Confirm email" setting is currently' not in spec


def test_private_launch_runbook_assigns_app_origin_and_smtp_secret_correctly() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    ownership = runbook.split("## Render Environment Ownership", 1)[1].split(
        "## Runtime Tuning Flags", 1
    )[0]
    ownership_text = " ".join(ownership.split())

    assert "Both `argus-app` and `argus-api`" in ownership_text
    assert "password-recovery redirects" in ownership_text
    assert "approval signup links" in ownership_text
    assert "`ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD`" in ownership_text


def test_execution_realism_contract_is_consistent_across_canon_and_release_docs() -> None:
    for path in (
        "docs/PRODUCT.md",
        "docs/ARCHITECTURE.md",
        "docs/API_CONTRACT.md",
        "docs/PRIVATE_LAUNCH_RUNBOOK.md",
        "docs/specs/private-alpha-next-roadmap.md",
    ):
        source = " ".join(_source(path).split())

        assert "ARGUS_ENABLE_EXECUTION_REALISM" in source
        assert "active by default" in source
        assert "costs remain opt-in per idea" in source
        assert "`false|0|off|no`" in source


def test_api_contract_does_not_exclude_supported_execution_costs() -> None:
    source = " ".join(_source("docs/API_CONTRACT.md").split())

    assert "slippage, fees, order queue modeling" not in source
    assert "Modeled fees and slippage are supported when a user opts in" in source


def test_private_alpha_release_manifest_template_has_required_audit_fields() -> None:
    template = _source("docs/release-manifests/TEMPLATE.md")
    canary_checks = json.loads(RELEASE_PROFILE_PATH.read_text(encoding="utf-8"))[
        "canary"
    ]["required_steps"]

    for check in canary_checks:
        assert f"`{check}`" in template
    for expected in (
        "Candidate SHA",
        "Promotion target",
        "Rollback target",
        "Approver",
        "api_web_env_fingerprint",
        "workflow_env_fingerprint",
        "workflow_env_status",
        "workflow_runtime_provider_mode",
        "workflow_runtime_proof",
        "env_fingerprint",
        "workflow_task",
        "real_workflow_task",
        "Backtest service mode",
        "Workflow service proof",
        "Secret rotation / least-privilege owner",
        "Canary evidence",
        "Failed-capture replay",
        "Release profile hash",
        "Browser signup/login proof",
        "private-alpha-release-coherence-evidence",
        "private-alpha-authenticated-browser-evidence",
        "No raw conversation, user, run, or job ids",
        "sanitized replay inputs",
    ):
        assert expected in template


def test_dated_release_manifest_distinguishes_workflow_tasks() -> None:
    manifest = _source(
        "docs/release-manifests/2026-07-14-private-alpha-release-integrity.md"
    )

    assert "- Workflow proof task: `argus-backtests/workflow_proof`" in manifest
    assert "- Real workflow task: `argus-backtests/run_backtest_job`" in manifest


def test_private_alpha_integration_doc_points_to_current_gate_and_later_memo() -> None:
    integration = _source("docs/specs/private-alpha-next-integration.md")

    assert "docs/specs/private-alpha-ci-cd-sota.md" in integration
    assert "docs/specs/private-alpha-next-decision-memo.md" in integration
    assert "later-context only" in integration
    assert "no production deploy happens from this branch" in integration.lower()
    assert "release manifest" in integration
    assert "Private Alpha Canary" in integration
    assert "local smoke" in integration
    assert "workflow_runtime_proof=ready" in integration


def test_agents_guardrail_keeps_canary_evidence_before_main_promotion() -> None:
    agents = _source("AGENTS.md")

    assert "docs/specs/private-alpha-ci-cd-sota.md" in agents
    assert "branch-deployed staging/private-alpha Render validation surface" in agents
    assert "Do not treat merge to `main` as a prerequisite for canary" in agents
    assert "`main` is the later promotion target" in agents


def test_eval_docs_document_mocked_first_test_tiers_and_agent_pointer() -> None:
    readme = _source("tests/evals/README.md")
    agents = _source("AGENTS.md")

    assert "## Test Tiers" in readme
    assert "**Mocked harness - every change (free, no API calls):**" in readme
    assert "poetry run pytest tests/evals/test_measurement_eval_harness.py" in readme
    assert "Validates routing, scorecard provenance, live-environment refusal" in readme
    assert "full conversation-step manifests" in readme
    assert "**Live eval - only the 3 sanctioned moments:**" in readme
    assert "Pre-merge on a PR that changes runtime behavior" in readme
    assert "Main promotion candidate" in readme
    assert "After any model/provider change" in readme
    assert "**Browser QA is also real-API:**" in readme
    assert "ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider" in readme
    assert "ARGUS_ASSET_PROVIDER_MODE=live_provider" in readme
    for provenance_field in (
        "market_data_provider_mode",
        "asset_provider_mode",
        "candidate_sha",
        "python_version",
        "fixture_sha256",
        "fixture_case_ids",
        "worktree_clean",
        "live_market_data_probe",
    ):
        assert provenance_field in readme

    assert "tests/evals/README.md" in agents
    assert "mocked harness" in agents
    assert "live eval" in agents
    assert "Browser QA" in agents
