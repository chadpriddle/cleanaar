import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from faster_whisper import WhisperModel

APP = "cleanarr"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(APP)

WATCH_DIR = Path(os.getenv("CLEANARR_WATCH_DIR", "/watch"))
OUTPUT_DIR = Path(os.getenv("CLEANARR_OUTPUT_DIR", "/movies"))
ARCHIVE_DIR = Path(os.getenv("CLEANARR_ARCHIVE_DIR", "/watch/.processed"))
MODEL = os.getenv("CLEANARR_MODEL", "medium.en")
DEVICE = os.getenv("CLEANARR_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("CLEANARR_COMPUTE_TYPE", "int8")
LANGUAGE = os.getenv("CLEANARR_LANGUAGE", "en")
SCAN_INTERVAL = int(os.getenv("CLEANARR_SCAN_INTERVAL", "30"))
STABLE_SECONDS = int(os.getenv("CLEANARR_STABLE_SECONDS", "120"))
PROGRESS_STEP = max(1, int(os.getenv("CLEANARR_PROGRESS_STEP", "2")))
PAD_BEFORE = float(os.getenv("CLEANARR_PADDING_BEFORE", "0.10"))
PAD_AFTER = float(os.getenv("CLEANARR_PADDING_AFTER", "0.18"))
ARCHIVE_ORIGINAL = os.getenv("CLEANARR_ARCHIVE_ORIGINAL", "true").lower() in {"1","true","yes","on"}
PRESERVE_ORIGINAL_AUDIO = os.getenv("CLEANARR_PRESERVE_ORIGINAL_AUDIO", "true").lower() in {"1","true","yes","on"}
CLEAN_TRACK_TITLE = os.getenv("CLEANARR_CLEAN_TRACK_TITLE", "English - Clean (AI, Muted)")

CONFIG_DIR = Path("/config")
PROFANITY_FILE = CONFIG_DIR / "profanity.txt"
STATE_DIR = WATCH_DIR / ".cleanarr"
STATE_FILE = STATE_DIR / "state.json"
READY_FILE = Path("/tmp/cleanarr-ready")

STATE_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
READY_FILE.unlink(missing_ok=True)


def load_bad_words():
    if not PROFANITY_FILE.exists():
        raise FileNotFoundError(f"Missing profanity list: {PROFANITY_FILE}")
    words = set()
    for line in PROFANITY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            words.add(line)
    return words


BAD_WORDS = load_bad_words()


def fmt(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def normalize(word):
    return re.sub(r"[^a-z0-9']", "", word.lower()).strip("'")


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def fingerprint(path):
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def is_stable(path):
    return time.time() - path.stat().st_mtime >= STABLE_SECONDS


def discover():
    for path in WATCH_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".mkv":
            continue
        if STATE_DIR in path.parents or ARCHIVE_DIR in path.parents:
            continue
        if path.name.endswith(".partial.mkv"):
            continue
        yield path


def merge_intervals(intervals):
    if not intervals:
        return []
    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + 0.08:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(x) for x in merged]


def transcribe(model, source):
    log.info("Transcribing: %s", source)
    segments, info = model.transcribe(
        str(source),
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
    )
    total = max(float(info.duration), 0.001)
    log.info("Audio duration %s | language=%s (%.2f)", fmt(total), info.language, info.language_probability)

    started = time.monotonic()
    next_pct = PROGRESS_STEP
    intervals = []
    matches = []

    for segment in segments:
        media_time = max(0.0, float(segment.end))
        pct = min(100.0, media_time / total * 100.0)

        while pct >= next_pct:
            elapsed = time.monotonic() - started
            speed = media_time / elapsed if elapsed > 0 else 0
            eta = (total - media_time) / speed if speed > 0 else 0
            log.info(
                "Transcription %d%% | media %s/%s | elapsed %s | ETA %s | %.1fx realtime",
                min(next_pct, 100), fmt(media_time), fmt(total), fmt(elapsed), fmt(eta), speed,
            )
            next_pct += PROGRESS_STEP

        for word in segment.words or []:
            cleaned = normalize(word.word)
            if cleaned in BAD_WORDS:
                start = max(0.0, float(word.start) - PAD_BEFORE)
                end = float(word.end) + PAD_AFTER
                intervals.append((start, end))
                matches.append({"word": cleaned, "start": round(start, 3), "end": round(end, 3)})

    elapsed = time.monotonic() - started
    log.info("Transcription 100%% | elapsed %s | matches=%d", fmt(elapsed), len(matches))
    return merge_intervals(intervals), matches, total


def mute_expression(intervals):
    return "+".join(f"between(t\\,{a:.3f}\\,{b:.3f})" for a, b in intervals)


def build_output(source, target, intervals, duration):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial.mkv")
    partial.unlink(missing_ok=True)

    if intervals:
        expr = mute_expression(intervals)
        filter_graph = (
            f"[0:a:0]volume='if(gt({expr}\\,0)\\,0\\,1)':eval=frame[clean]"
        )
        args = [
            "-filter_complex", filter_graph,
            "-map", "0:v?",
            "-map", "[clean]",
        ]
        if PRESERVE_ORIGINAL_AUDIO:
            args += ["-map", "0:a?"]
        args += [
            "-map", "0:s?",
            "-map", "0:t?",
            "-c", "copy",
            "-c:a:0", "aac",
            "-b:a:0", "384k",
            "-metadata:s:a:0", "language=eng",
            "-metadata:s:a:0", f"title={CLEAN_TRACK_TITLE}",
            "-disposition:a:0", "default",
        ]
    else:
        args = ["-map", "0", "-c", "copy"]

    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(source),
        *args,
        "-map_metadata", "0",
        "-map_chapters", "0",
        "-progress", "pipe:1",
        "-nostats",
        str(partial),
    ]

    log.info("Writing: %s", target)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    last_logged = -10

    for line in proc.stdout or []:
        line = line.strip()
        if line.startswith("out_time_us="):
            try:
                current = int(line.split("=", 1)[1]) / 1_000_000
                pct = min(100, int(current / duration * 100))
                if pct >= last_logged + 10:
                    log.info("FFmpeg %d%% complete", pct)
                    last_logged = pct
            except ValueError:
                pass

    code = proc.wait()
    if code != 0:
        partial.unlink(missing_ok=True)
        raise subprocess.CalledProcessError(code, cmd)

    partial.replace(target)
    log.info("FFmpeg 100%% complete")


def archive_source(source, relative):
    if not ARCHIVE_ORIGINAL:
        return None
    destination = ARCHIVE_DIR / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        destination = destination.with_name(f"{destination.stem}.{timestamp}{destination.suffix}")

    shutil.move(str(source), str(destination))
    return destination


def process(model, source):
    relative = source.relative_to(WATCH_DIR)
    target = OUTPUT_DIR / relative

    intervals, matches, duration = transcribe(model, source)
    build_output(source, target, intervals, duration)

    archived = archive_source(source, relative)

    report = {
        "source": str(source),
        "output": str(target),
        "archived_original": str(archived) if archived else None,
        "matches": len(matches),
        "detected_words": matches,
        "model": MODEL,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
    }
    target.with_suffix(target.suffix + ".cleanarr.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    log.info("FINISHED: %s", target)
    if archived:
        log.info("Archived original: %s", archived)


def main():
    log.info("Cleanarr starting")
    log.info("Loaded %d filter words from %s", len(BAD_WORDS), PROFANITY_FILE)
    log.info("Loading model=%s device=%s compute_type=%s", MODEL, DEVICE, COMPUTE_TYPE)

    model = WhisperModel(
        MODEL,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        download_root="/models",
    )

    READY_FILE.touch()
    state = load_state()
    log.info("Watching %s", WATCH_DIR)
    log.info("Completed movies go to %s", OUTPUT_DIR)
    log.info("Original archive: %s", ARCHIVE_DIR if ARCHIVE_ORIGINAL else "disabled")

    while True:
        found = False
        for source in discover():
            found = True
            try:
                if not is_stable(source):
                    continue

                fp = fingerprint(source)
                if state.get(str(source)) == fp:
                    continue

                process(model, source)
                state[str(source)] = fp
                save_state(state)

            except Exception:
                log.exception("Processing failed for %s", source)

        if not found:
            log.debug("No MKV files found.")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
