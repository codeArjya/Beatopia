"""Worker entrypoint (WS1): poll `jobs` every 1 s, claim with `for update skip locked`, run `stems` / `analyze`.

Config comes only from env (DATABASE_URL, SUPABASE_*, DEMUCS_MODEL) so the container stays simple.
"""


def main() -> None:
    raise NotImplementedError("WS1: worker loop (see CONTRACT §3 job shapes)")


if __name__ == "__main__":
    main()
