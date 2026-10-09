# RecordScope research MVP

Standalone public-source research app on the `public-records-research-mvp` branch. This branch deploys to https://recordscope-research.onrender.com and does not change other applications or the repository's main branch.

## Coverage

- Historical collection records: Library of Congress public JSON API, first 15 results.
- Court opinions: CourtListener v4, first 15 results, requires `COURTLISTENER_API_TOKEN`. CourtListener is a nonprofit archive rather than the issuing court. PACER and state directory links remain available.
- Public companies: SEC company directory and up to 10 recent filings from the first matching company, requires `SEC_USER_AGENT` with a contact header the operator authorizes. CIK queries accept e.g. `CIK 320193`. Registrations for private businesses remain at state registries.
- National Archives, FamilySearch, Ancestry and other portals are explicitly labeled research links. The app does not retrieve records behind subscriptions or logins.

Retrieved records include original source URLs and provenance. They are not independently verified facts or identity matches. There is no generated AI summary in this version.

## Change monitoring

Watches and snapshots are stored in the user's browser, with a maximum of 10 watches. Checks compare limited result windows on demand and every 15 minutes while the page remains open. The first successful check establishes a baseline; later checks count additions, changes and records that left the result window. An unavailable or unconfigured source does not overwrite its last successful snapshot. Checks use a 60-second cache. This is not an always-on server scheduler or an exhaustive record monitor. Clearing browser storage removes watches.

The old globally shared SQLite watch endpoints are retired with HTTP 410. Historical shared watches are not displayed or migrated.

## Run and test

```
pip install -r requirements.txt
python app.py
pip install pytest
python -m pytest tests -q
```

Render start command: `gunicorn app:app --bind 0.0.0.0:$PORT`. Free hosting may sleep while unused. Configure API credentials through Render environment variables; do not commit secrets.

## Primary source documentation

- https://www.loc.gov/apis/json-and-yaml/requests/endpoints/
- https://www.loc.gov/apis/json-and-yaml/responses/search-results/
- https://wiki.free.law/c/courtlistener/help/api/rest/v4/search
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
