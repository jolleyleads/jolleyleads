"""Minimal WSGI deployment wrapper for the OmniScope neural core.

Chat remains disabled unless OMNISCOPE_ACCESS_TOKEN and OMNISCOPE_MODEL are set.
This starter expects Ollama on loopback; production requires a separately
provisioned inference service and an authenticated provider adapter.
"""
import hmac
import json
import os
from urllib.error import URLError

from omniscope_brain import Brain


ROADMAP = [
    {"phase": 1, "name": "Neural Core", "status": "starter implemented",
     "deliverables": ["Direct evidence-focused personality", "Local Ollama adapter",
                      "Bounded in-memory conversation", "Deployment health API"],
     "acceptance": "Evaluate factuality, uncertainty, source honesty, and tone against a fixed question set."},
    {"phase": 2, "name": "Sensory Inputs", "status": "planned",
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
            "service": "healthy", "inference": "not provisioned on this service",
            "web_retrieval": False, "gps": False, "people_search": False,
            "image_generation": False, "code_execution": False,
            "roadmap": "/api/roadmap"})
    if method == "GET" and path == "/api/roadmap":
        return respond("200 OK", ROADMAP)
    if method != "POST" or path != "/api/chat":
        return respond("404 Not Found", {"error": "Endpoint not found"})
    token = os.environ.get("OMNISCOPE_ACCESS_TOKEN", "")
    if not token:
        return respond("503 Service Unavailable", {"error": "Chat access is not configured"})
    supplied = environ.get("HTTP_AUTHORIZATION", "")
    if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
        return respond("401 Unauthorized", {"error": "Authentication required"})
    model = os.environ.get("OMNISCOPE_MODEL", "")
    if not model:
        return respond("503 Service Unavailable", {"error": "Inference model is not configured"})
    try:
        size = int(environ.get("CONTENT_LENGTH", "0"))
        if not 0 < size <= 16384:
            return respond("413 Payload Too Large", {"error": "Body must be 1 to 16384 bytes"})
        payload = json.loads(environ["wsgi.input"].read(size))
        if not isinstance(payload, dict):
            raise ValueError("Expected object")
        question = payload.get("message")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Expected nonempty message")
        # A fresh brain prevents accidental cross-user history sharing.
        answer = Brain(model).ask(question)
        return respond("200 OK", {"answer": answer})
    except (ValueError, UnicodeError):
        return respond("400 Bad Request", {"error": "Invalid JSON message"})
    except (URLError, TimeoutError):
        return respond("503 Service Unavailable", {"error": "Inference unavailable"})

