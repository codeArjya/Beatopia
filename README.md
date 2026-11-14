# Beatopia

Sample discovery for newer producers: smart search over a curated Creative Commons library, a preview of the
suggested window, optional stems, a browser chop editor, and WAV export.

Start with `AGENTS.md`, then `docs/CONTRACT.md` and `docs/SETUP.md`.

```bash
cp .env.example .env    # fill in
make install            # uv sync x4 + pnpm install
make dev-api            # :8000, answers from fixtures at bootstrap
make dev-web            # :3000
```
