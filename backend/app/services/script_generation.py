import logging
import re
from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.knowledge_base import KBFact, KBLimitation
from app.models.project import Project, ProjectSlide, ProjectSlideScript

log = logging.getLogger(__name__)


@dataclass
class GenerationOptions:
    feedback: str | None = None
    make_shorter: bool = False
    more_energy: bool = False
    more_citations: bool = False
    preserve_approved_neighbors: bool = True


@dataclass
class SlideGenerationResult:
    narration: str
    segments: list[dict]
    citations: list[dict]
    duration_seconds: int
    delivery_style: dict
    running_summary: str
    context: dict = field(default_factory=dict)


def generate_project_scripts(project: Project, db: Session) -> list[ProjectSlideScript]:
    scripts: list[ProjectSlideScript] = []
    running_summary = ""
    total = len(project.slides)
    facts = _project_facts(project, db)
    limitations = _project_limitations(project, db)

    for index, slide in enumerate(project.slides, start=1):
        result = generate_slide_script(
            project=project,
            slide=slide,
            db=db,
            running_summary=running_summary,
            section=_section(index, total),
            facts=facts,
            limitations=limitations,
        )
        script = upsert_slide_script(slide, result)
        db.add(script)
        scripts.append(script)
        running_summary = result.running_summary

    return scripts


def regenerate_slide_script(
    project: Project,
    slide: ProjectSlide,
    db: Session,
    options: GenerationOptions,
) -> ProjectSlideScript:
    slides = list(project.slides)
    index = slides.index(slide) + 1
    previous_summary = _previous_running_summary(slides, index)
    result = generate_slide_script(
        project=project,
        slide=slide,
        db=db,
        running_summary=previous_summary,
        section=_section(index, len(slides)),
        facts=_project_facts(project, db),
        limitations=_project_limitations(project, db),
        options=options,
    )
    script = upsert_slide_script(slide, result, feedback=options.feedback)
    db.add(script)
    return script


def generate_slide_script(
    project: Project,
    slide: ProjectSlide,
    db: Session,  # noqa: ARG001
    running_summary: str,
    section: str,
    facts: list[KBFact],
    limitations: list[KBLimitation],
    options: GenerationOptions | None = None,
) -> SlideGenerationResult:
    options = options or GenerationOptions()
    relevant_facts = _relevant_facts(slide, facts)
    relevant_limitations = _relevant_limitations(slide, limitations)
    citations = _citations(project, relevant_facts, relevant_limitations)
    tone = project.tone_profile or {}
    energy = _energy_for(section, options.more_energy)

    try:
        narration = _generate_narration(
            slide=slide,
            section=section,
            running_summary=running_summary,
            tone=tone,
            energy=energy,
            facts=relevant_facts,
            limitations=relevant_limitations,
            options=options,
        )
        if _is_bad_narration(narration):
            narration = _fallback_narration(
                slide,
                section,
                running_summary,
                facts=relevant_facts,
                limitations=relevant_limitations,
                options=options,
            )
    except Exception:
        log.exception("LLM narration failed for slide %s, using fallback", slide.id)
        narration = _fallback_narration(
            slide,
            section,
            running_summary,
            facts=relevant_facts,
            limitations=relevant_limitations,
            options=options,
        )

    segments = _segments(narration, energy, tone)
    duration_seconds = _duration_seconds(narration, tone.get("pace", "normal"))
    running_summary_out = _update_summary(running_summary, slide.title or "", slide.body, relevant_facts)
    context = {
        "slide_context": slide.generation_context,
        "kb_ids": [link.kb_id for link in project.knowledge_bases],
        "structured_fact_count": len(relevant_facts),
        "limitation_count": len(relevant_limitations),
        "section": section,
    }

    return SlideGenerationResult(
        narration=narration,
        segments=segments,
        citations=citations,
        duration_seconds=duration_seconds,
        delivery_style={
            "persona": tone.get("persona", "helpful presenter"),
            "formality": tone.get("formality", "balanced"),
            "pace": tone.get("pace", "normal"),
            "energy": energy,
            "audio_tags": sorted({tag for segment in segments for tag in segment["audio_tags"]}),
        },
        running_summary=running_summary_out,
        context=context,
    )


def upsert_slide_script(
    slide: ProjectSlide,
    result: SlideGenerationResult,
    feedback: str | None = None,
) -> ProjectSlideScript:
    if slide.script:
        script = slide.script
        script.version += 1
    else:
        script = ProjectSlideScript(slide=slide)

    script.status = "draft"
    script.narration = result.narration
    script.segments = result.segments
    script.citations = result.citations
    script.duration_seconds = result.duration_seconds
    script.delivery_style = result.delivery_style
    script.running_summary = result.running_summary
    script.feedback = feedback
    return script


# --- LLM generation ---

def _generate_narration(
    slide: ProjectSlide,
    section: str,
    running_summary: str,
    tone: dict,
    energy: str,
    facts: list[KBFact],
    limitations: list[KBLimitation],
    options: GenerationOptions,
) -> str:
    persona = tone.get("persona", "helpful presenter")
    formality = tone.get("formality", "balanced")
    pace = tone.get("pace", "normal")

    section_instruction = {
        "intro": "This is the opening slide. Hook the audience, establish stakes, and frame the story arc.",
        "middle": "This is a body slide. Build on what's been covered, connect this point to the bigger picture, and set up what comes next.",
        "close": "This is the closing slide. Land the core takeaway with confidence and leave a memorable final thought.",
    }[section]

    system = f"""You write a presenter's spoken narration for one slide of a presentation.

Write what the PRESENTER SAYS — not what the slide shows.

Rules:
- Write for the ear: contractions, direct address ("you", "we"), punchy sentences
- Never say "This slide shows", "As you can see", "The slide says", "the main point here is", or reference the slide
- Never mention internal context like "vision pass", "rendered image", "extracted text", "speaker notes", or "feedback"
- Don't read bullet points aloud — interpret them, expand the idea, tell the "so what"
- Add presenter value: frame why this matters, explain implications, give a natural transition
- Weave verified facts in naturally; never list them mechanically
- Persona: {persona}. Formality: {formality}. Pace: {pace}. Energy: {energy}
- Target: 3–5 sentences (30–45 seconds spoken)
- {section_instruction}
- If feedback is given, the output must directly reflect it"""

    lines = [f"Slide title: {slide.title or 'Untitled'}"]

    if slide.body:
        lines.append(f"Slide content (context only — do not read aloud): {slide.body[:600]}")

    if slide.notes:
        lines.append(f"Speaker notes: {slide.notes[:400]}")

    vision = slide.vision_summary or ""
    if vision and not _is_stub_vision(vision):
        lines.append(f"Visual elements (images, charts, diagrams on the slide): {vision[:400]}")

    if running_summary:
        lines.append(f"Story so far (for coherence): {running_summary[-350:]}")

    if facts:
        facts_text = "\n".join(f"- {f.key}: {f.value}" for f in facts[:3])
        lines.append(f"Verified facts to weave in:\n{facts_text}")

    if limitations:
        limits_text = "; ".join(item.description for item in limitations[:2])
        lines.append(f"Do not claim beyond: {limits_text}")

    if options.feedback:
        lines.append(f"Feedback to apply: {options.feedback}")

    if options.make_shorter:
        lines.append("Keep it brief — 2–3 sentences maximum.")

    if options.more_energy:
        lines.append("High energy — be punchy, enthusiastic, direct.")

    client = OpenAI(api_key=get_settings().OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(lines)},
        ],
        temperature=0.75,
        max_tokens=300,
    )
    return (response.choices[0].message.content or "").strip()


def _is_stub_vision(vision: str) -> bool:
    stub_markers = ("Vision pass completed", "Rendered image stored", "Rendered image is")
    return any(marker in vision for marker in stub_markers)


def _is_bad_narration(narration: str) -> bool:
    text = narration.lower()
    banned = (
        "vision pass",
        "rendered image",
        "extracted text",
        "speaker note",
        "revision note",
        "feedback",
        "this slide shows",
        "the slide says",
        "the main point here is",
        "visually,",
        "as you can see",
    )
    return not narration.strip() or any(phrase in text for phrase in banned)


def _fallback_narration(
    slide: ProjectSlide,
    section: str,
    running_summary: str,
    facts: list[KBFact] | None = None,
    limitations: list[KBLimitation] | None = None,
    options: GenerationOptions | None = None,
) -> str:
    facts = facts or []
    limitations = limitations or []
    options = options or GenerationOptions()
    title = _clean(slide.title) or f"Slide {slide.position}"
    idea = _speaker_idea(slide)
    fact_phrase = _natural_fact_phrase(facts)
    boundary = _natural_boundary_phrase(limitations)

    if section == "intro":
        sentences = [
            f"Today, we're framing {title} as a practical path, not just a topic.",
            f"The goal is to help the audience understand what changes when {idea}.",
            fact_phrase,
            "From here, we can move from the big promise into the concrete capabilities that make it real.",
        ]
    elif section == "close":
        sentences = [
            f"The takeaway is simple: {title} should leave people with a clear next step.",
            f"By this point, the story has moved from context to action, so the audience should know why {idea}.",
            fact_phrase,
            boundary,
            "That gives us a strong place to pause, take questions, and connect the message back to their needs.",
        ]
    else:
        transition = (
            "Building on the story so far, "
            if running_summary
            else "The next idea is "
        )
        sentences = [
            f"{transition}{title} helps turn the concept into something the audience can use.",
            f"Instead of treating this as a checklist, frame it around what becomes easier, safer, or more repeatable when {idea}.",
            fact_phrase,
            boundary,
            "That keeps the presentation moving from information toward confidence.",
        ]

    if options.more_energy:
        sentences[0] = sentences[0].replace("helps", "really helps")
    if options.feedback:
        sentences.append(_feedback_guidance_sentence(options.feedback))

    cleaned = [sentence for sentence in sentences if sentence]
    if options.make_shorter:
        cleaned = cleaned[:3]
    return " ".join(cleaned)


def _speaker_idea(slide: ProjectSlide) -> str:
    body = _clean(slide.body)
    title = _clean(slide.title)
    source = body or title or "this capability is introduced"
    source = re.sub(r"^(a|an|the)\s+", "", source, flags=re.IGNORECASE)
    if ":" in source:
        before, after = source.split(":", 1)
        after = after.strip()
        if after.lower().startswith("from "):
            source = f"learners can move {after}"
        else:
            source = f"{before.strip()} becomes practical through {after}"
    if len(source) > 170:
        source = source[:167].rsplit(" ", 1)[0] + "..."
    source = source.rstrip(" .")
    return source[0].lower() + source[1:] if source else "this capability is introduced"


def _natural_fact_phrase(facts: list[KBFact]) -> str:
    if not facts:
        return ""
    fact = facts[0]
    return f"One useful anchor for credibility is {fact.key}: {fact.value}, which gives the audience something specific to remember."


def _natural_boundary_phrase(limitations: list[KBLimitation]) -> str:
    if not limitations:
        return ""
    return f"Keep the claim disciplined: {limitations[0].description}."


def _feedback_guidance_sentence(feedback: str) -> str:
    text = feedback.lower()
    if "example" in text:
        return "A quick concrete example will make this feel less abstract for the room."
    if "executive" in text:
        return "Keep the emphasis on business impact and decisions, not implementation detail."
    if "explain" in text or "explanation" in text:
        return "Make the reasoning explicit so the audience understands the why, not only the what."
    if "concise" in text or "short" in text:
        return "Keep the phrasing tight and let the strongest idea carry the moment."
    return "Use a little more interpretation here so the audience hears the message behind the content."


# --- Supporting logic (unchanged) ---

def _project_facts(project: Project, db: Session) -> list[KBFact]:
    kb_ids = [link.kb_id for link in project.knowledge_bases]
    if not kb_ids:
        return []
    return db.query(KBFact).filter(KBFact.kb_id.in_(kb_ids)).all()


def _project_limitations(project: Project, db: Session) -> list[KBLimitation]:
    kb_ids = [link.kb_id for link in project.knowledge_bases]
    if not kb_ids:
        return []
    return db.query(KBLimitation).filter(KBLimitation.kb_id.in_(kb_ids)).all()


def _relevant_facts(slide: ProjectSlide, facts: list[KBFact]) -> list[KBFact]:
    haystack = _slide_haystack(slide)
    matches = [
        fact
        for fact in facts
        if _tokens(fact.key) & _tokens(haystack)
        or _tokens(fact.value) & _tokens(haystack)
    ]
    return (matches or facts)[:3]


def _relevant_limitations(slide: ProjectSlide, limitations: list[KBLimitation]) -> list[KBLimitation]:
    haystack = _slide_haystack(slide)
    matches = [
        item
        for item in limitations
        if _tokens(item.description) & _tokens(haystack)
    ]
    return matches[:2]


def _citations(
    project: Project,
    facts: list[KBFact],
    limitations: list[KBLimitation],
) -> list[dict]:
    pinned = {link.kb_id: link.pinned_version for link in project.knowledge_bases}
    fact_citations = [
        {
            "id": fact.id,
            "type": "structured_fact",
            "kb_id": fact.kb_id,
            "kb_version": pinned.get(fact.kb_id),
            "label": fact.key,
            "value": fact.value,
            "source": fact.source or "KB structured facts",
        }
        for fact in facts
    ]
    limitation_citations = [
        {
            "id": item.id,
            "type": "limitation",
            "kb_id": item.kb_id,
            "kb_version": pinned.get(item.kb_id),
            "label": "limitation",
            "value": item.description,
            "source": "KB limitations",
        }
        for item in limitations
    ]
    return fact_citations + limitation_citations


def _section(index: int, total: int) -> str:
    if index == 1:
        return "intro"
    if index == total:
        return "close"
    return "middle"


def _energy_for(section: str, more_energy: bool) -> str:
    if more_energy:
        return "high"
    return {"intro": "warm", "middle": "steady", "close": "confident"}[section]


def _segments(narration: str, energy: str, tone: dict) -> list[dict]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narration) if s.strip()]
    segments: list[dict] = []
    for index, sentence in enumerate(sentences, start=1):
        tag = "beat" if index > 1 else "start"
        if index == len(sentences):
            tag = "resolve"
        segments.append(
            {
                "index": index,
                "text": sentence,
                "delivery": {
                    "style": tone.get("persona", "helpful presenter"),
                    "energy": energy,
                    "prosody": "conversational, short phrases, clear pauses",
                },
                "audio_tags": [tag, f"energy:{energy}", f"pace:{tone.get('pace', 'normal')}"],
            }
        )
    return segments


def _duration_seconds(narration: str, pace: str) -> int:
    words = len(narration.split())
    wpm = {"slow": 120, "normal": 145, "brisk": 165}.get(pace, 145)
    return max(8, round(words / wpm * 60))


def _update_summary(running_summary: str, title: str, body: str, facts: list[KBFact]) -> str:
    fact_keys = ", ".join(fact.key for fact in facts[:2])
    addition = f"{title}: {body[:120]}"
    if fact_keys:
        addition += f" (facts: {fact_keys})"
    combined = f"{running_summary} {addition}".strip()
    return combined[-700:]


def _previous_running_summary(slides: list[ProjectSlide], index: int) -> str:
    previous = [slide.script.running_summary for slide in slides[: index - 1] if slide.script]
    return previous[-1] if previous else ""


def _slide_haystack(slide: ProjectSlide) -> str:
    return " ".join(
        part
        for part in (
            slide.title or "",
            slide.body,
            slide.notes,
            slide.vision_summary,
        )
        if part
    ).lower()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9$%.]+", text.lower()) if len(token) > 2}


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())
