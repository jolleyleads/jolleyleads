# OmniScope neural core

This is a Phase 1 starter with provider adapters, not a completed multimodal platform. The deployed
WSGI service exposes health, capability status, and the four-phase roadmap.
No model credentials or GPU have been provisioned. Its chat endpoint fails closed until
authentication and a provider are configured. No hidden external provider
or account credentials are bundled.

## Run locally

Install Ollama and download a suitable chat model using its official setup.
Run `python omniscope_brain.py --model YOUR_INSTALLED_MODEL`.
The CLI keeps the most recent eight turns in RAM. `/reset` clears history.
Python 3.10 or later is required. The CLI has no Python package dependencies.

## Deployment

Build: `pip install -r requirements.txt && python -m unittest -v`

Start: `gunicorn omniscope_service:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 200`

GET `/healthz`: web process health, not inference readiness.
GET `/api/status`: honest capability inventory.
GET `/api/roadmap`: phased deliverables and acceptance criteria.
GET `/api/integrations`: credential presence and missing environment key names;
never includes key values. Configured is explicitly different from live verified.
POST `/api/chat`: authenticated, single-turn OpenAI Responses call.
POST `/api/places/search`: Google Places Text Search (New), with `query`,
`page_size` (1 to 20), and optional `page_token`.
POST `/api/people/contacts`: authorized Google contacts, with `page_size`
(1 to 100) and optional `page_token`.
Every POST requires `Authorization: Bearer <OMNISCOPE_ACCESS_TOKEN>`.

## Provider configuration

Set secrets in the OmniScope Render service environment, never in GitHub.
The service is the source of truth for configuration, not a Blueprint.
No operation here exports ChatGPT connector credentials.

| Integration | Required environment variables | External prerequisite |
| --- | --- | --- |
| API access | OMNISCOPE_ACCESS_TOKEN | A long random server access secret |
| OpenAI | OPENAI_API_KEY, OPENAI_MODEL | API account with access to that model and available quota |
| Google Places | GOOGLE_PLACES_API_KEY | Places API (New) enabled, correct restrictions and billing |
| Google People | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_PEOPLE_REFRESH_TOKEN | People API enabled; owner OAuth consent for contacts.readonly and offline access |
| GitHub deployment | OMNISCOPE_SOURCE_REPOSITORY, OMNISCOPE_SOURCE_BRANCH | Already linked through Render; not a runtime GitHub access token |

The exact contacts scope is `https://www.googleapis.com/auth/contacts.readonly`.
The Google refresh token must belong to this OAuth client and consenting account.
Token acquisition and consent UX are not implemented; the adapter refreshes an
already provisioned token on demand. Google People is not an arbitrary people
search or genealogy service. Places coordinates describe businesses/places,
not live device locations. Provider responses, contacts, and credentials are
never written to application logs by this code.

Requests to Google Places can incur charges. The narrow field mask includes
attributions; display them alongside Google data in any future UI. This service
does not persist Places results. Review current Google display/attribution terms
before building that UI.

The public Render deployment does not run Ollama. Local-only fallback uses
OMNISCOPE_PROVIDER=ollama plus OMNISCOPE_MODEL and local Ollama.
The default provider is OpenAI. Chat does not automatically invoke the separate
Places or People endpoints or send contacts to OpenAI.
Authentication UX, quotas, OAuth consent UX, and persistent per-user state remain work.

## Architecture and roadmap

The orchestrator should route requests to separately permissioned services.
Prompt instructions are not a security boundary. Enforce authorization in code.

1. Neural Core: versioned persona, provider adapter, session handling, and
   factuality/uncertainty evaluations. Initial code is present; live inference
   and behavioral evaluations are pending; an OpenAI adapter is implemented.
2. Sensory Inputs: search/retrieval, source timestamps, deduplication, opt-in
   device coordinates, geocoding, and licensed biographical/genealogy sources.
   A geocoding API does not track people. Do not infer a person's live location
   from a name or phone number. Separate same-name identity candidates.
3. Visual Engine: SDXL in a separate GPU worker, queue, job status, object
   storage, consent controls, and generated-image provenance. SDXL cannot
   guarantee anatomical accuracy. Do not build nonconsensual intimate imagery.
4. Execution Layer: disposable isolated Python sandboxes with resource/time
   limits, no host secrets, and disabled network by default. Authorize lab
   cybersecurity tasks explicitly. Do not execute generated Python with eval,
   exec, or an unrestricted subprocess inside the web application.

## Source references

- https://docs.ollama.com/api/chat
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- https://render.com/docs/web-services
- https://developers.openai.com/api/docs/guides/text
- https://developers.google.com/maps/documentation/places/web-service/text-search
- https://developers.google.com/people/api/rest/v1/people.connections/list

The architecture is a proposal. Model behavior, retrieval quality, image quality,
cost, and security isolation require separate evaluation before production use.
