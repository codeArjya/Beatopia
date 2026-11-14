"""The 20 eval queries (PLAN.md T3.2/T4.3/T6.3): text-only, chips-only and text + chips. (text, chip ids)."""

EVAL_QUERIES: list[tuple[str | None, list[str]]] = [
    ("dusty soul keys", []),
    ("sad trumpet around 90 bpm, no drums", []),
    ("warm rhodes chords", []),
    ("funky wah guitar riff", []),
    ("jazzy upright bass line", []),
    ("dark cinematic strings", []),
    ("lo-fi piano with vinyl crackle", []),
    ("chopped soul vocals", []),
    ("boom bap drum break", []),
    ("latin percussion groove", []),
    ("eerie flute melody", []),
    ("bright brass stabs", []),
    ("kazoo orchestra", []),  # nonsense: expected to need the Freesound fallback
    (None, ["inst.rhodes", "genre.soul"]),
    (None, ["genre.hip_hop", "tempo.90"]),
    (None, ["mood.melancholy"]),
    (None, ["inst.piano", "key.a_minor"]),
    ("dreamy synth pad", ["mood.chill"]),
    ("disco strings", ["tempo.120"]),
    ("organ groove", ["genre.funk", "mood.groovy"]),
]
