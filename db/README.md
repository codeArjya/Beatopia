# db/ (owner: **WS1**)

`migrations/NNN_*.sql`, applied in filename order by `scripts/db_init.py` (`make db-init`), which records applied files in
`schema_migrations` and creates the public Storage bucket `audio`. `001_init.sql` is CONTRACT §3 verbatim: schema
changes that affect other streams need a contract proposal first.
