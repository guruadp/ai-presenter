import html
import io
import os
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True)
class ParsedSlide:
    position: int
    title: str | None
    body: str
    notes: str


def is_pptx(filename: str, content_type: str | None) -> bool:
    return filename.lower().endswith(".pptx") or content_type in {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }


def parse_pptx(content: bytes) -> list[ParsedSlide]:
    try:
        return _parse_with_python_pptx(content)
    except ImportError:
        return _parse_with_xml(content)
    except Exception as e:
        raise ValueError("Invalid PPTX file") from e


def render_slide_images(slides: list[ParsedSlide], output_dir: str) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    image_paths: list[str] = []
    for slide in slides:
        path = Path(output_dir) / f"slide_{slide.position}.png"
        _render_preview_png(slide, path)
        image_paths.append(str(path))
    return image_paths


def _parse_with_python_pptx(content: bytes) -> list[ParsedSlide]:
    try:
        from pptx import Presentation
    except ImportError as e:
        raise e

    prs = Presentation(io.BytesIO(content))
    slides: list[ParsedSlide] = []
    for index, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(shape.text.strip())
        notes = ""
        if slide.has_notes_slide:
            notes = "\n".join(
                paragraph.text.strip()
                for paragraph in slide.notes_slide.notes_text_frame.paragraphs
                if paragraph.text.strip()
            )
        title = texts[0] if texts else None
        body = "\n".join(texts[1:] if title else texts)
        slides.append(ParsedSlide(position=index, title=title, body=body, notes=notes))
    return slides


def _parse_with_xml(content: bytes) -> list[ParsedSlide]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        raise ValueError("Invalid PPTX file") from e

    slide_names = sorted(
        (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
        key=lambda name: int(re.search(r"slide(\d+)\.xml", name).group(1)),  # type: ignore[union-attr]
    )
    if not slide_names:
        raise ValueError("PPTX contains no slides")

    slides: list[ParsedSlide] = []
    for index, slide_name in enumerate(slide_names, start=1):
        texts = _extract_text_nodes(archive.read(slide_name))
        title = texts[0] if texts else None
        body = "\n".join(texts[1:] if title else texts)
        slides.append(ParsedSlide(position=index, title=title, body=body, notes=""))
    return slides


def _extract_text_nodes(xml_bytes: bytes) -> list[str]:
    root = ElementTree.fromstring(xml_bytes)
    texts = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text and node.text.strip():
            texts.append(html.unescape(node.text.strip()))
    return texts


def _render_preview_png(slide: ParsedSlide, path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        _write_basic_png(path)
        return

    width, height = 1280, 720
    image = Image.new("RGB", (width, height), color=(250, 252, 255))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.load_default(size=36)
        body_font = ImageFont.load_default(size=22)
        small_font = ImageFont.load_default(size=18)
    except TypeError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.rectangle((0, 0, width, 72), fill=(31, 41, 55))
    draw.text((36, 22), f"Slide {slide.position}", fill=(255, 255, 255), font=small_font)

    y = 115
    if slide.title:
        draw.multiline_text((64, y), _wrap(slide.title, 52), fill=(17, 24, 39), font=title_font, spacing=8)
        y += 100

    body = slide.body or "No body text extracted from this slide."
    draw.multiline_text((64, y), _wrap(body, 90), fill=(55, 65, 81), font=body_font, spacing=8)

    if slide.notes:
        draw.text((64, height - 64), "Speaker notes available", fill=(75, 85, 99), font=small_font)

    image.save(path, "PNG")


def _write_basic_png(path: Path) -> None:
    width, height = 1280, 720
    row = b"\x00" + (b"\xfa\xfc\xff" * width)
    raw = row * height

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk("IHDR".encode(), struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk("IDAT".encode(), zlib.compress(raw))
        + chunk("IEND".encode(), b"")
    )
    path.write_bytes(png)


def _wrap(text: str, limit: int) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        words = raw_line.split()
        current: list[str] = []
        for word in words:
            if sum(len(part) for part in current) + len(current) + len(word) > limit:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
    return "\n".join(lines)
