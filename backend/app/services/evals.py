import re
from dataclasses import dataclass, field

from app.services.qa import AnswerResult


@dataclass(frozen=True)
class ScriptEvalCase:
    name: str
    narration: str
    kb_facts: list[str] = field(default_factory=list)
    tone_profile: dict = field(default_factory=dict)


@dataclass(frozen=True)
class QAEvalCase:
    name: str
    question: str
    answer: AnswerResult
    expected_answer_terms: list[str] = field(default_factory=list)
    kb_facts: list[str] = field(default_factory=list)
    out_of_scope: bool = False


@dataclass(frozen=True)
class MetricResult:
    score: float
    passed: bool
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalReport:
    hallucination_rate: MetricResult
    factual_accuracy: MetricResult
    tone_adherence: MetricResult
    answer_correctness: MetricResult
    feasibility_overclaim: MetricResult
    release_gate: MetricResult

    def as_dict(self) -> dict:
        return {
            "hallucination_rate": _metric_dict(self.hallucination_rate),
            "factual_accuracy": _metric_dict(self.factual_accuracy),
            "tone_adherence": _metric_dict(self.tone_adherence),
            "answer_correctness": _metric_dict(self.answer_correctness),
            "feasibility_overclaim": _metric_dict(self.feasibility_overclaim),
            "release_gate": _metric_dict(self.release_gate),
        }


DEFAULT_THRESHOLDS = {
    "max_hallucination_rate": 0.10,
    "min_factual_accuracy": 0.85,
    "min_tone_adherence": 0.80,
    "min_answer_correctness": 0.80,
    "max_feasibility_overclaim_rate": 0.0,
}

_BAD_TONE_PATTERNS = (
    "the slide says",
    "this slide shows",
    "as you can see",
    "vision pass",
    "rendered image",
    "extracted text",
    "speaker note",
    "revision note",
)

_OVERCLAIM_PATTERNS = (
    r"\byes\b",
    r"\bdefinitely\b",
    r"\bwill\b",
    r"\bcan do\b",
    r"\bsupports?\b",
    r"\bguaranteed\b",
    r"\bno problem\b",
)

_DEFERRAL_PATTERNS = (
    "explore that specific use case",
    "team would",
    "follow up",
    "not documented",
    "don't have that specific detail",
    "most accurate answer",
)


def run_eval_suite(
    script_cases: list[ScriptEvalCase],
    qa_cases: list[QAEvalCase],
    thresholds: dict | None = None,
) -> EvalReport:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    hallucination = evaluate_hallucination(script_cases, qa_cases, thresholds["max_hallucination_rate"])
    factual = evaluate_factual_accuracy(script_cases, qa_cases, thresholds["min_factual_accuracy"])
    tone = evaluate_tone_adherence(script_cases, thresholds["min_tone_adherence"])
    correctness = evaluate_answer_correctness(qa_cases, thresholds["min_answer_correctness"])
    feasibility = evaluate_feasibility_overclaim(qa_cases, thresholds["max_feasibility_overclaim_rate"])

    gate_details = []
    for name, metric in (
        ("hallucination_rate", hallucination),
        ("factual_accuracy", factual),
        ("tone_adherence", tone),
        ("answer_correctness", correctness),
        ("feasibility_overclaim", feasibility),
    ):
        if not metric.passed:
            gate_details.append(f"{name} failed: {metric.details[:3]}")

    return EvalReport(
        hallucination_rate=hallucination,
        factual_accuracy=factual,
        tone_adherence=tone,
        answer_correctness=correctness,
        feasibility_overclaim=feasibility,
        release_gate=MetricResult(
            score=1.0 if not gate_details else 0.0,
            passed=not gate_details,
            details=gate_details,
        ),
    )


def evaluate_hallucination(
    script_cases: list[ScriptEvalCase],
    qa_cases: list[QAEvalCase],
    max_rate: float = DEFAULT_THRESHOLDS["max_hallucination_rate"],
) -> MetricResult:
    unsupported = []
    total = 0
    for case in script_cases:
        claims = _claim_terms(case.narration)
        total += len(claims)
        unsupported.extend(
            f"{case.name}: unsupported claim term '{claim}'"
            for claim in claims
            if not _supported(claim, case.kb_facts)
        )
    for case in qa_cases:
        claims = _claim_terms(case.answer.answer)
        total += len(claims)
        unsupported.extend(
            f"{case.name}: unsupported answer claim term '{claim}'"
            for claim in claims
            if not _supported(claim, case.kb_facts)
        )
    rate = len(unsupported) / total if total else 0.0
    return MetricResult(score=round(rate, 4), passed=rate <= max_rate, details=unsupported)


def evaluate_factual_accuracy(
    script_cases: list[ScriptEvalCase],
    qa_cases: list[QAEvalCase],
    min_score: float = DEFAULT_THRESHOLDS["min_factual_accuracy"],
) -> MetricResult:
    checks = []
    failures = []
    for case in script_cases:
        for fact in case.kb_facts:
            if _important_fact(fact):
                checks.append(fact)
                if _normalize(fact) not in _normalize(case.narration):
                    failures.append(f"{case.name}: missing/altered fact '{fact}'")
    for case in qa_cases:
        for fact in case.kb_facts:
            if _important_fact(fact):
                checks.append(fact)
                if _normalize(fact) not in _normalize(case.answer.answer):
                    failures.append(f"{case.name}: answer missing/altered fact '{fact}'")
    score = 1.0 - (len(failures) / len(checks)) if checks else 1.0
    return MetricResult(score=round(score, 4), passed=score >= min_score, details=failures)


def evaluate_tone_adherence(
    script_cases: list[ScriptEvalCase],
    min_score: float = DEFAULT_THRESHOLDS["min_tone_adherence"],
) -> MetricResult:
    failures = []
    for case in script_cases:
        text = case.narration.lower()
        for pattern in _BAD_TONE_PATTERNS:
            if pattern in text:
                failures.append(f"{case.name}: non-presenter wording '{pattern}'")
        persona = str(case.tone_profile.get("persona", "")).lower()
        if persona and "executive" in persona and len(case.narration.split()) > 130:
            failures.append(f"{case.name}: executive tone is too long")
    score = 1.0 - (len(failures) / max(1, len(script_cases)))
    score = max(0.0, score)
    return MetricResult(score=round(score, 4), passed=score >= min_score, details=failures)


def evaluate_answer_correctness(
    qa_cases: list[QAEvalCase],
    min_score: float = DEFAULT_THRESHOLDS["min_answer_correctness"],
) -> MetricResult:
    failures = []
    checked = 0
    for case in qa_cases:
        if case.out_of_scope:
            continue
        checked += 1
        answer = _normalize(case.answer.answer)
        missing = [term for term in case.expected_answer_terms if _normalize(term) not in answer]
        if missing:
            failures.append(f"{case.name}: missing expected terms {missing}")
        if case.answer.deferred and not case.out_of_scope:
            failures.append(f"{case.name}: incorrectly deferred in-scope answer")
    score = 1.0 - (len(failures) / checked) if checked else 1.0
    score = max(0.0, score)
    return MetricResult(score=round(score, 4), passed=score >= min_score, details=failures)


def evaluate_feasibility_overclaim(
    qa_cases: list[QAEvalCase],
    max_rate: float = DEFAULT_THRESHOLDS["max_feasibility_overclaim_rate"],
) -> MetricResult:
    out_of_scope = [case for case in qa_cases if case.out_of_scope]
    overclaims = []
    for case in out_of_scope:
        answer = case.answer.answer.lower()
        deferred = case.answer.deferred or any(pattern in answer for pattern in _DEFERRAL_PATTERNS)
        claims_yes = any(re.search(pattern, answer) for pattern in _OVERCLAIM_PATTERNS)
        if claims_yes and not deferred:
            overclaims.append(f"{case.name}: over-claimed feasibility")
    rate = len(overclaims) / len(out_of_scope) if out_of_scope else 0.0
    return MetricResult(score=round(rate, 4), passed=rate <= max_rate, details=overclaims)


def default_regression_suite() -> tuple[list[ScriptEvalCase], list[QAEvalCase]]:
    script_cases = [
        ScriptEvalCase(
            name="presenter_tone",
            narration="Today, we frame the training program as a practical path from safe operation to confident presentation.",
            kb_facts=["training program"],
            tone_profile={"persona": "helpful presenter"},
        ),
        ScriptEvalCase(
            name="exact_fact",
            narration="One useful anchor is ARR: $4.2M, which gives the audience a concrete business signal.",
            kb_facts=["$4.2M"],
            tone_profile={"persona": "executive presenter"},
        ),
    ]
    qa_cases = [
        QAEvalCase(
            name="product_fact",
            question="What is ARR?",
            answer=AnswerResult(
                answer="ARR is $4.2M, so that is the concrete number to remember.",
                question_type="product-fact",
                citations=[{"source": "pricing.md"}],
                confidence=0.9,
                deferred=False,
            ),
            expected_answer_terms=["$4.2M"],
            kb_facts=["$4.2M"],
        ),
        QAEvalCase(
            name="out_of_scope_feasibility",
            question="Can it autonomously operate any robot in any factory?",
            answer=AnswerResult(
                answer="That use case is not documented here. The team would be happy to explore that specific use case with you.",
                question_type="feasibility",
                citations=[],
                confidence=0.4,
                deferred=True,
                deferred_reason="out of scope",
            ),
            out_of_scope=True,
        ),
    ]
    return script_cases, qa_cases


def run_default_regression_suite() -> EvalReport:
    scripts, qa = default_regression_suite()
    return run_eval_suite(scripts, qa)


def _claim_terms(text: str) -> list[str]:
    terms = set()
    for pattern in (
        r"\$[\d,.]+[kKmMbB]?",
        r"\b\d+(?:\.\d+)?\s?%",
        r"\b(?:19|20)\d{2}\b",
        r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){1,3}\b",
    ):
        terms.update(match.group(0).strip() for match in re.finditer(pattern, text))
    return sorted(terms)


def _supported(claim: str, kb_facts: list[str]) -> bool:
    claim_norm = _normalize(claim)
    return any(claim_norm in _normalize(fact) or _normalize(fact) in claim_norm for fact in kb_facts)


def _important_fact(fact: str) -> bool:
    return bool(re.search(r"\$|\d|%", fact))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _metric_dict(metric: MetricResult) -> dict:
    return {"score": metric.score, "passed": metric.passed, "details": metric.details}
