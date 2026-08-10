# Contributing to Cleanarr

Thanks for considering a contribution.

## Before opening a pull request

1. Open or reference an issue for substantial behavior changes.
2. Keep changes focused.
3. Do not commit copyrighted media samples.
4. Do not commit model files, API keys, secrets, or personal media paths.
5. Preserve backwards-compatible environment variables when practical.

## Development

```bash
cp .env.example .env
docker compose up -d --build
docker logs -f cleanarr
```

For NVIDIA GPU testing:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

## Good first contributions

- tests for profanity normalization
- configurable source audio stream
- phrase matching
- improved processing state
- better progress reporting
- documentation
- sample `.env` profiles
- Plex/Jellyfin integrations

## Pull requests

Please include:

- what changed
- why it changed
- how you tested it
- any compatibility impact
- relevant logs for Docker/GPU changes

By submitting a contribution, you agree that it may be distributed under the MIT License.
