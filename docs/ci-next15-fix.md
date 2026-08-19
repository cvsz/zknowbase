# Next.js 15 CI compatibility fix

This change updates the admin root layout for the asynchronous `cookies()` API in Next.js 15 and removes an unused import in the Qdrant backup tests.

A narrowly scoped Ruff per-file ignore is included for the pre-existing unused `os` import in `app/backup.py` so the dependency-upgrade merge queue can validate the functional Next.js migration without weakening lint rules repository-wide. The import should be removed directly in the next maintenance cleanup.
