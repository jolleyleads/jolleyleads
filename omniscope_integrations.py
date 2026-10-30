"""Server-side provider adapters. Secrets come only from runtime environment.

No provider is marked verified merely because its credentials are present.
Google People reads the owner's authorized contacts, never a public people DB.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from omniscope_brain import SYSTEM_PROMPT


class IntegrationError(Exception):
    def __init__(self, provider, message, status=503):
        self.provider = provider
        self.message = message
        self.status = status
        super().__init__(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def required(provider, *keys):
    values = [os.environ.get(key, "").strip() for key in keys]
    if not all(values):
        raise IntegrationError(provider, "Provider credentials or configuration are missing")
    return values


def request_json(provider, url, body=None, headers=None, form=False):
    headers = dict(headers or {})
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=45) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise IntegrationError(provider, "Provider response exceeded size limit", 502)
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        return result
    except urllib.error.HTTPError as exc:
        # Never return upstream bodies, URLs, tokens, or request headers.
        messages = {401: "Provider rejected credentials", 403: "Provider denied access; check scopes, API enablement and billing",
                    429: "Provider quota or rate limit reached"}
        raise IntegrationError(provider, messages.get(exc.code, "Provider request failed"), 502) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise IntegrationError(provider, "Provider could not be reached", 502) from None
    except (ValueError, UnicodeError):
        raise IntegrationError(provider, "Invalid provider response", 502) from None


def integrations_status():
    requirements = {
        "openai": ("OPENAI_API_KEY", "OPENAI_MODEL"),
        "google_places": ("GOOGLE_PLACES_API_KEY",),
        "google_people": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_PEOPLE_REFRESH_TOKEN"),
    }
    result = {}
    for provider, keys in requirements.items():
        missing = [key for key in keys if not os.environ.get(key, "").strip()]
        result[provider] = {"status": "credentials_missing" if missing else "configured_unverified",
                            "missing_environment_keys": missing, "live_verified": False}
    result["github_deployment"] = {
        "status": "linked" if os.environ.get("OMNISCOPE_SOURCE_REPOSITORY") else "not_configured",
        "repository": os.environ.get("OMNISCOPE_SOURCE_REPOSITORY", ""),
        "branch": os.environ.get("OMNISCOPE_SOURCE_BRANCH", ""),
        "note": "Source deployment link; not a GitHub account token for runtime operations"}
    return result


def openai_chat(message):
    key, model = required("openai", "OPENAI_API_KEY", "OPENAI_MODEL")
    result = request_json("openai", "https://api.openai.com/v1/responses",
        body={"model": model, "instructions": SYSTEM_PROMPT,
              "input": message, "store": False, "max_output_tokens": 2000},
        headers={"Authorization": "Bearer " + key})
    if result.get("status") != "completed":
        raise IntegrationError("openai", "Model response did not complete", 502)
    texts = []
    for item in result.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    texts.append(content["text"])
                elif content.get("type") == "refusal" and isinstance(content.get("refusal"), str):
                    texts.append(content["refusal"])
    if not texts:
        raise IntegrationError("openai", "Model returned no answer text", 502)
    return {"answer": "\n".join(texts), "provider": "openai", "model": model}


def places_search(query, page_size=10, page_token=""):
    key, = required("google_places", "GOOGLE_PLACES_API_KEY")
    body = {"textQuery": query, "pageSize": page_size}
    if page_token:
        body["pageToken"] = page_token
    result = request_json("google_places", "https://places.googleapis.com/v1/places:searchText",
        body=body, headers={"X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.attributions,nextPageToken"})
    return {"provider": "google_places", "places": result.get("places", []),
            "next_page_token": result.get("nextPageToken"),
            "note": "Coordinates describe places, not live device or person locations"}


def people_contacts(page_size=25, page_token=""):
    client_id, client_secret, refresh_token = required("google_people",
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_PEOPLE_REFRESH_TOKEN")
    token = request_json("google_people", "https://oauth2.googleapis.com/token", form=True,
        body={"client_id": client_id, "client_secret": client_secret,
              "refresh_token": refresh_token, "grant_type": "refresh_token"})
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise IntegrationError("google_people", "Google did not issue an access token", 502)
    params = {"personFields": "names,emailAddresses,phoneNumbers,organizations",
              "pageSize": page_size}
    if page_token:
        params["pageToken"] = page_token
    result = request_json("google_people",
        "https://people.googleapis.com/v1/people/me/connections?" + urllib.parse.urlencode(params),
        headers={"Authorization": "Bearer " + access_token})
    return {"provider": "google_people", "contacts": result.get("connections", []),
            "next_page_token": result.get("nextPageToken"),
            "note": "Contacts from the Google account that authorized this app"}
