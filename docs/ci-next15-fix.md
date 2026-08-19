# Next.js 15 CI compatibility fix

This change updates the admin root layout for the asynchronous `cookies()` API in Next.js 15 and removes the unused import in the Qdrant backup test.

The backend CI fixes also make backup archives owner-only (`0600`) after creation and isolate the Postgres queue ownership test from state left by earlier integration tests. No repository-wide lint suppression is required.
