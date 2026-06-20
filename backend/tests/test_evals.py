from app.services.evals import (
    QAEvalCase,
    ScriptEvalCase,
    evaluate_feasibility_overclaim,
    evaluate_tone_adherence,
    run_default_regression_suite,
    run_eval_suite,
)
from app.services.qa import AnswerResult


def test_default_regression_suite_passes_release_gate():
    report = run_default_regression_suite()

    assert report.release_gate.passed
    assert report.hallucination_rate.passed
    assert report.factual_accuracy.passed
    assert report.tone_adherence.passed
    assert report.answer_correctness.passed
    assert report.feasibility_overclaim.passed
    assert report.as_dict()["release_gate"]["passed"] is True


def test_tone_eval_rejects_slide_reader_language():
    result = evaluate_tone_adherence(
        [
            ScriptEvalCase(
                name="bad_reader",
                narration="This slide shows the training program. The slide says G1 and Go2.",
            )
        ],
        min_score=0.8,
    )

    assert not result.passed
    assert any("this slide shows" in detail for detail in result.details)


def test_feasibility_metric_catches_overclaim_on_out_of_scope_case():
    result = evaluate_feasibility_overclaim(
        [
            QAEvalCase(
                name="overclaim",
                question="Can this operate any factory robot autonomously?",
                answer=AnswerResult(
                    answer="Yes, it definitely supports any factory robot with no problem.",
                    question_type="feasibility",
                    citations=[],
                    confidence=0.2,
                    deferred=False,
                ),
                out_of_scope=True,
            )
        ]
    )

    assert not result.passed
    assert result.score == 1.0


def test_release_gate_fails_for_missing_expected_answer_terms():
    report = run_eval_suite(
        script_cases=[
            ScriptEvalCase(
                name="ok_script",
                narration="Today, we frame the program as a practical path.",
                kb_facts=[],
            )
        ],
        qa_cases=[
            QAEvalCase(
                name="wrong_answer",
                question="What is ARR?",
                answer=AnswerResult(
                    answer="ARR is not available here.",
                    question_type="product-fact",
                    citations=[],
                    confidence=0.9,
                    deferred=False,
                ),
                expected_answer_terms=["$4.2M"],
                kb_facts=["$4.2M"],
            )
        ],
    )

    assert not report.release_gate.passed
    assert not report.answer_correctness.passed
