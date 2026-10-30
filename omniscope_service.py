"""OmniScope WSGI API. Provider endpoints require server-side authentication."""
import hmac
import json
import os
from urllib.error import URLError

from omniscope_brain import Brain
from omniscope_integrations import (IntegrationError, integrations_status,
                                    openai_chat, places_search, people_contacts)


ROADMAP = [
    {"phase": 1, "name": "Neural Core", "status": "starter implemented",
     "deliverables": ["Direct evidence-focused personality", "OpenAI and local Ollama adapters",
                      "Bounded in-memory conversation", "Deployment health API"],
     "acceptance": "Evaluate factuality, uncertainty, source honesty, and tone against a fixed question set."},
    {"phase": 2, "name": "Sensory Inputs", "status": "Places and People adapters implemented; credentials pending; other inputs planned",
     "deliverables": ["Current web retrieval with source URLs and timestamps",
                      "Opt-in device coordinates and geocoding",
                      "Licensed professional and genealogy sources with identity checks"],
     "acceptance": "Citations resolve; same-name people stay distinct; permission revocation stops location collection."},
    {"phase": 3, "name": "Visual Engine", "status": "planned",
     "deliverables": ["Separate GPU worker running SDXL via Diffusers",
                      "Queued jobs and durable image storage", "Consent and provenance records"],
     "acceptance": "Measure image quality and job reliability; reject nonconsensual intimate imagery. Anatomy is not guaranteed."},
    {"phase": 4, "name": "Execution Layer", "status": "planned",
     "deliverables": ["Ephemeral isolated Python sandboxes", "CPU, memory, time and output limits",
                      "No default network or host secrets", "Authorized security labs and calculation tools"],
     "acceptance": "Verify isolation, forced termination, blocked secret access, and reproducible results."},
]


def app(environ, start_response):
    def respond(status, value):
        data = json.dumps(value).encode()
        start_response(status, [("Content-Type", "application/json; charset=utf-8"),
                                ("Content-Length", str(len(data))),
                                ("Cache-Control", "no-store"),
                                ("X-Content-Type-Options", "nosniff")])
        return [data]

    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    if method == "GET" and path in ("/", "/healthz", "/api/status"):
        return respond("200 OK", {"name": "OmniScope", "phase": 1,
            "service": "healthy", "inference": integrations_status()["openai"]["status"],
            "web_retrieval": False, "gps": False, "people_search": False,
            "image_generation": False, "code_execution": False,
            "roadmap": "/api/roadmap", "integrations": "/api/integrations",
            "note": "Provider adapters exist; credentials configured does not mean live verified"})
    if method == "GET" and path == "/api/integrations":
        return respond("200 OK", integrations_status())
    if method == "GET" and path == "/api/roadmap":
        return respond("200 OK", ROADMAP)
    routes = ("/api/chat", "/api/places/search", "/api/people/contacts")
    if method != "POST" or path not in routes:
        return respond("404 Not Found", {"error": "Endpoint not found"})
    token = os.environ.get("OMNISCOPE_ACCESS_TOKEN", "")
    if not token:
        return respond("503 Service Unavailable", {"error": "API access is not configured"})
    supplied = environ.get("HTTP_AUTHORIZATION", "")
    if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
        return respond("401 Unauthorized", {"error": "Authentication required"})
    try:
        size = int(environ.get("CONTENT_LENGTH", "0"))
        if not 0 < size <= 16384:
            return respond("413 Payload Too Large", {"error": "Body must be 1 to 16384 bytes"})
        payload = json.loads(environ["wsgi.input"].read(size))
        if not isinstance(payload, dict):
            raise ValueError("Expected object")
    except (ValueError, UnicodeError):
        return respond("400 Bad Request", {"error": "Invalid JSON message"})
    try:
        if path == "/api/chat":
            question = payload.get("message")
            if not isinstance(question, str) or not 0 < len(question.strip()) <= 12000:
                raise ValueError("message must contain 1 to 12000 characters")
            if os.environ.get("OMNISCOPE_PROVIDER", "openai") == "ollama":
                model = os.environ.get("OMNISCOPE_MODEL", "")
                if not model:
                    raise IntegrationError("ollama", "Local model is not configured")
                return respond("200 OK", {"answer": Brain(model).ask(question), "provider": "ollama"})
            return respond("200 OK", openai_chat(question))
        page_size = payload.get("page_size", 10 if path == "/api/places/search" else 25)
        maximum = 20 if path == "/api/places/search" else 100
        if type(page_size) is not int or not 1 <= page_size <= maximum:
            raise ValueError(f"page_size must be an integer from 1 to {maximum}")
        page_token = payload.get("page_token", "")
        if not isinstance(page_token, str) or len(page_token) > 8192:
            raise ValueError("Invalid page_token")
        if path == "/api/people/contacts":
            return respond("200 OK", people_contacts(page_size, page_token))
        query = payload.get("query")
        if not isinstance(query, str) or not 0 < len(query.strip()) <= 512:
            raise ValueError("query must contain 1 to 512 characters")
        return respond("200 OK", places_search(query, page_size, page_token))
    except IntegrationError as exc:
        label = "Bad Gateway" if exc.status == 502 else "Service Unavailable"
        return respond(f"{exc.status} {label}", {"provider": exc.provider, "error": exc.message})
    except ValueError as exc:
        return respond("400 Bad Request", {"error": str(exc)})
    except (URLError, TimeoutError):
        return respond("503 Service Unavailable", {"error": "Inference unavailable"})

