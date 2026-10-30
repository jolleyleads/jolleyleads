# OmniScope neural core

This is a Phase 1 starter, not a completed multimodal platform. The deployed
WSGI service exposes health, capability status, and the four-phase roadmap.
No model or GPU has been provisioned. Its chat endpoint fails closed until
authentication and local inference are configured. No hidden external provider
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
POST `/api/chat`: authenticated, single-turn model call; disabled by default.
Local-only configuration: OMNISCOPE_ACCESS_TOKEN and OMNISCOPE_MODEL.
The public Render deployment does not run Ollama. A production inference
adapter, authentication UX, quotas, and persistent per-user state remain work.

## Architecture and roadmap

The orchestrator should route requests to separately permissioned services.
Prompt instructions are not a security boundary. Enforce authorization in code.

1. Neural Core: versioned persona, provider adapter, session handling, and
   factuality/uncertainty evaluations. Initial code is present; live inference
   and behavioral evaluations are pending.
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

The architecture is a proposal. Model behavior, retrieval quality, image quality,
cost, and security isolation require separate evaluation before production use.
