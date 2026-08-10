# Cleanarr

AI-assisted profanity muting for self-hosted media libraries.

Cleanarr watches a folder for MKV files, transcribes dialogue with Faster-Whisper, finds words in a configurable profanity list, creates a clean audio track with those words muted, preserves the original video/audio/subtitles, and writes the finished MKV into your media library.

> **Status:** v1.0 / early community release. Test on copies of media before relying on it for a large library.

## Features

- Recursive MKV folder watching
- Faster-Whisper transcription
- CPU mode
- NVIDIA CUDA GPU mode
- Word-level timestamps
- Profanity muting (no bleep tone)
- Percentage, elapsed-time, realtime-speed, and ETA logs
- Preserves original video without re-encoding
- Preserves original audio tracks by default
- Preserves subtitles, chapters, metadata, and attachments
- Writes a new clean audio track as the default track
- Preserves source folder structure
- Moves successfully processed originals to `.processed/`
- JSON report beside each completed MKV
- Editable `config/profanity.txt` mounted into the container
- No OpenAI API key required

## How it works

```text
/watch/Movie Name/Movie.mkv
        |
        v
Faster-Whisper transcription
        |
        v
Exact-word profanity matching
        |
        v
FFmpeg creates muted clean audio
        |
        +----> /movies/Movie Name/Movie.mkv
        |
        +----> /watch/.processed/Movie Name/Movie.mkv
```

The video stream is copied, not re-encoded. The generated clean audio track is encoded as AAC. Original audio tracks remain in the MKV unless disabled.

## Quick start

```bash
git clone https://github.com/YOUR-USERNAME/cleanarr.git
cd cleanarr
cp .env.example .env
nano .env
./scripts/install.sh cpu
```

Follow logs:

```bash
docker logs -f cleanarr
```

### NVIDIA GPU

Install the NVIDIA driver and NVIDIA Container Toolkit first, then:

```bash
./scripts/install.sh gpu
```

Check GPU activity:

```bash
watch -n 1 nvidia-smi
```

The included GPU profile uses CUDA 12.2 + cuDNN 8 and CTranslate2 4.4.0. `int8_float32` is the default GPU compute type because it works on older cards that do not efficiently support `int8_float16`.

## Configuration

Copy `.env.example` to `.env` and edit it.

Important settings:

| Variable | Default | Purpose |
|---|---|---|
| `WATCH_DIR` | `/data/plex/whisper` | Host incoming folder |
| `OUTPUT_DIR` | `/data/plex/movies` | Host completed-media folder |
| `CLEANARR_MODEL` | `medium.en` | Faster-Whisper model |
| `CLEANARR_LANGUAGE` | `en` | Transcription language |
| `CLEANARR_STABLE_SECONDS` | `120` | Wait until incoming file stops changing |
| `CLEANARR_PROGRESS_STEP` | `2` | Transcription log percentage interval |
| `CLEANARR_PADDING_BEFORE` | `0.10` | Extra mute time before detected word |
| `CLEANARR_PADDING_AFTER` | `0.18` | Extra mute time after detected word |
| `CLEANARR_ARCHIVE_ORIGINAL` | `true` | Move successful source into `.processed` |
| `CLEANARR_PRESERVE_ORIGINAL_AUDIO` | `true` | Keep all original audio tracks |

## Profanity list

Edit:

```text
config/profanity.txt
```

One exact word per line. Matching is case-insensitive.

Because the file is mounted into the container, you do **not** need to rebuild the image after changing it:

```bash
docker restart cleanarr
```

The current matcher intentionally uses exact words rather than substrings, so `ass` will not match `class`.

## Folder behavior

Example source:

```text
/data/plex/whisper/Office.Space.1999/Office.Space.1999.mkv
```

Successful output:

```text
/data/plex/movies/Office.Space.1999/Office.Space.1999.mkv
```

Archived original:

```text
/data/plex/whisper/.processed/Office.Space.1999/Office.Space.1999.mkv
```

Subfolders are preserved.

## Logs

```bash
docker logs -f cleanarr
```

Example:

```text
Transcription 40% | media 00:35:42/01:29:15 | elapsed 00:05:15 | ETA 00:07:53 | 6.8x realtime
...
Transcription 100% | matches=37
FFmpeg 10% complete
...
FFmpeg 100% complete
FINISHED: /movies/Office.Space.1999/Office.Space.1999.mkv
```

## Limitations

Speech recognition is imperfect. Cleanarr can miss profanity, mute the wrong word, or produce imperfect mute boundaries. Background music, overlapping dialogue, accents, slang, and low-quality audio can reduce accuracy.

The default implementation creates the clean track from the **first audio stream**. Multi-language and commentary-heavy MKVs may require explicit audio-track selection in a future release.

This is not an official Plex, Jellyfin, OpenAI, Whisper, FFmpeg, NVIDIA, Radarr, or Sonarr project.

## Roadmap

Contributions are welcome, especially for:

- G / PG / PG-13 filtering profiles
- Phrase matching
- configurable audio-stream selection
- subtitle-assisted detection
- Plex/Jellyfin refresh integration
- Radarr/Sonarr integration
- web UI
- per-library profiles
- processing queue / history
- tests
- ARM support
- additional languages

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
