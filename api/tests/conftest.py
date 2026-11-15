import os

# Tests that import `app.main.app` get fixture mode (no DB/CLAP/Gemini). Real-mode tests build their own app with
# `create_app(Settings.from_env({...}))`.
os.environ.setdefault("USE_FIXTURES", "1")
