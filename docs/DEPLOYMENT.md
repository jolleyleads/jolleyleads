# Deployment

Render service: `recordscope-research`.
Repository: `jolleyleads/jolleyleads`.
Branch: `public-records-research-mvp`.
Build: `pip install -r requirements.txt`.
Start: `gunicorn app:app --bind 0.0.0.0:$PORT`.

Optional environment variables:
- `COURTLISTENER_API_TOKEN`: operator-provided CourtListener API token.
- `SEC_USER_AGENT`: operator-authorized contact identification for SEC requests. No account email is sent by default.

Changes must stay on this standalone branch. Render automatically deploys branch commits. Verify deploy status, `/health` version, homepage, search responses, and watch baselines and repeat comparisons. Missing credentials and source outages must be shown truthfully.
