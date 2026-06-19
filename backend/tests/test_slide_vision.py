from app.services.deck_ingestion import ParsedSlide
from app.services.slide_vision import build_generation_context, summarize_slide_image


def test_slide_vision_context_preserves_exact_text_boundary(tmp_path):
    image_path = tmp_path / "slide.png"
    image_path.write_bytes(b"not a real png, but present")
    slide = ParsedSlide(
        position=3,
        title="Revenue",
        body="$4.2M ARR",
        notes="Mention this exactly.",
    )

    summary = summarize_slide_image(str(image_path), slide)
    context = build_generation_context(slide, summary)

    assert "Vision pass completed" in summary
    assert context["extracted_text"]["title"] == "Revenue"
    assert context["extracted_text"]["body"] == "$4.2M ARR"
    assert context["vision_summary"] == summary
    assert context["merge_policy"]["exact_data_source"] == "extracted_text"
    assert context["merge_policy"]["visual_meaning_source"] == "vision_summary"
