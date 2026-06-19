from pathlib import Path

from app.services.deck_ingestion import ParsedSlide


def summarize_slide_image(image_path: str, slide: ParsedSlide) -> str:
    image_details = _image_details(image_path)
    visible_text = _visible_text(slide)
    parts = [
        "Vision pass completed for the rendered slide image.",
        image_details,
    ]
    if visible_text:
        parts.append(
            "Visible text extracted from the deck remains the source of truth: "
            f"{visible_text}."
        )
    parts.append(
        "Use this visual summary for layout, emphasis, and pixel-only cues; keep exact figures and claims from extracted text or KB citations."
    )
    return " ".join(part for part in parts if part)


def build_generation_context(slide: ParsedSlide, vision_summary: str) -> dict:
    return {
        "slide_number": slide.position,
        "extracted_text": {
            "title": slide.title,
            "body": slide.body,
            "notes": slide.notes,
        },
        "vision_summary": vision_summary,
        "merge_policy": {
            "exact_data_source": "extracted_text",
            "visual_meaning_source": "vision_summary",
        },
    }


def _visible_text(slide: ParsedSlide) -> str:
    text = " ".join(part for part in (slide.title, slide.body) if part)
    return text[:240]


def _image_details(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        return "No rendered image file was available for inspection."

    try:
        from PIL import Image
    except ImportError:
        return f"Rendered image stored at {path.name}."

    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return f"Rendered image stored at {path.name}."

    orientation = "landscape" if width >= height else "portrait"
    return f"Rendered image is {width}x{height}px in {orientation} orientation."
