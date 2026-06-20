import json
import os
import shutil
import subprocess
import tempfile


def export_show_video(project, show_file_id: str, output_path: str) -> None:
    """
    Build an MP4 from an existing Show File into *output_path*.
    Reuses pre-rendered audio + slide images from the bundle — no extra TTS calls.
    Caller is responsible for deleting output_path after serving it.
    """
    sf = next((sf for sf in project.show_files if sf.id == show_file_id), None)
    if sf is None:
        raise ValueError("Show file not found")

    # Resolve to absolute paths so FFmpeg concat lists work from any cwd
    manifest_abs = os.path.abspath(sf.manifest_path)
    with open(manifest_abs, encoding="utf-8") as f:
        manifest = json.load(f)

    show_dir = os.path.dirname(manifest_abs)
    slides = manifest.get("slides", [])
    if not slides:
        raise ValueError("Show file has no slides")

    with tempfile.TemporaryDirectory() as tmp:
        slide_videos: list[str] = []
        srt_entries: list[dict] = []
        global_t = 0.0

        for slide_idx, slide in enumerate(slides):
            image_abs = os.path.join(show_dir, slide["image_path"])
            segments = slide.get("segments", [])

            if not os.path.exists(image_abs) or not segments:
                continue

            # Collect segment audio paths + actual durations via ffprobe.
            # (manifest audio_duration_seconds can be wrong for streaming WAVs with bad RIFF headers)
            seg_rows: list[tuple[str, float, str]] = []
            for seg in segments:
                ap = os.path.join(show_dir, seg["audio_path"])
                if os.path.exists(ap):
                    seg_rows.append((ap, _probe_duration(ap), seg["text"]))

            if not seg_rows:
                continue

            # Merge segment WAVs into one slide WAV
            slide_wav = os.path.join(tmp, f"slide_{slide_idx}.wav")
            if len(seg_rows) == 1:
                shutil.copyfile(seg_rows[0][0], slide_wav)
            else:
                list_file = os.path.join(tmp, f"alist_{slide_idx}.txt")
                with open(list_file, "w") as lf:
                    for ap, _, _ in seg_rows:
                        lf.write(f"file '{ap}'\n")
                _ff(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", list_file, "-c", "copy", slide_wav])

            # Scale slide image to 1920×1080, letterbox with black bars
            img_scaled = os.path.join(tmp, f"img_{slide_idx}.png")
            _ff(["ffmpeg", "-y", "-i", image_abs,
                 "-vf", (
                     "scale=1920:1080:force_original_aspect_ratio=decrease,"
                     "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black"
                 ),
                 img_scaled])

            # Still-image + audio → per-slide MP4 at 25 fps (required for clean concat)
            slide_mp4 = os.path.join(tmp, f"slide_{slide_idx}.mp4")
            _ff(["ffmpeg", "-y",
                 "-loop", "1", "-i", img_scaled,
                 "-i", slide_wav,
                 "-c:v", "libx264", "-preset", "fast", "-tune", "stillimage",
                 "-r", "25",
                 "-c:a", "aac", "-b:a", "128k",
                 "-pix_fmt", "yuv420p",
                 "-shortest",
                 slide_mp4])
            slide_videos.append(slide_mp4)

            # SRT timing — use exact per-segment durations from the manifest
            for _, duration, text in seg_rows:
                srt_entries.append({"start": global_t, "end": global_t + duration, "text": text})
                global_t += duration

        if not slide_videos:
            raise ValueError("No slide videos could be generated; check that slide images and audio exist")

        # Concatenate + re-encode to normalise timestamps across slides
        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w") as cf:
            for v in slide_videos:
                cf.write(f"file '{v}'\n")
        concat_mp4 = os.path.join(tmp, "concat.mp4")
        _ff(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list,
             "-c:v", "libx264", "-preset", "fast",
             "-c:a", "aac", "-b:a", "128k",
             "-pix_fmt", "yuv420p",
             concat_mp4])

        # SRT subtitle file
        srt_path = os.path.join(tmp, "subs.srt")
        _write_srt(srt_path, srt_entries)

        # Mux subtitles as a soft text track into the final MP4
        _ff(["ffmpeg", "-y",
             "-i", concat_mp4,
             "-i", srt_path,
             "-c:v", "copy", "-c:a", "copy",
             "-c:s", "mov_text",
             "-metadata:s:s:0", "language=eng",
             output_path])


def _probe_duration(path: str) -> float:
    """Return actual audio duration via ffprobe (immune to bad RIFF headers)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return 0.0


def _ff(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg error:\n{result.stderr.decode(errors='replace')[-2000:]}"
        )


def _write_srt(path: str, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, e in enumerate(entries, 1):
            f.write(f"{i}\n")
            f.write(f"{_srt_ts(e['start'])} --> {_srt_ts(e['end'])}\n")
            f.write(f"{e['text'].strip()}\n\n")


def _srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
