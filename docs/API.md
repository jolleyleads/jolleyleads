# RecordScope API

- `GET /health`: service status and deployed version.
- `GET /api/sources`: research portal directory with URLs.
- `GET /api/search?q=Virginia&category=genealogy`: `results`, `sources`, `warnings`, `searched_at`, and provenance notice. Categories: `all`, `court`, `business`, `genealogy`. Query: 2–120 characters. `api_result` means retrieved source metadata; `source_link` means a portal link. `verified_record` remains false because retrieval does not independently verify accuracy.
- `POST /api/watches/check`: JSON `{ "query": "Virginia", "category": "genealogy", "previous": {} }`. Returns `snapshots`, `comparisons`, `checked_at`, and coverage notice. Pass returned snapshots as `previous` on the next check. Status is `baseline`, `compared`, `not_configured` or `unavailable`. Only successful source queries are compared; failures preserve earlier snapshots. Compared results include `added`, `removed` and `updated` source metadata. `removed` means outside the bounded query result window, not deletion at the source.
- `GET/POST /api/watches`: HTTP 410, browser-local watches replace the old globally shared list.

Requests have a 256 KiB body limit. No arbitrary URL fetching is supported.
