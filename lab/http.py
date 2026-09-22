"""Shared WSGI JSON transport, independent of any asset class or broker."""
import json


def wsgi_application(service):
    from urllib.parse import parse_qs
    from http import HTTPStatus

    def application(environ, start_response):
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        body = None
        headers = {"content-type": environ.get("CONTENT_TYPE", ""),
                   "authorization": environ.get("HTTP_AUTHORIZATION", "")}
        extra = {}
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length > 32768:
                status, payload = 413, {"error": "Request is too large"}
            else:
                if method == "POST":
                    raw = environ["wsgi.input"].read(length)
                    try:
                        body = json.loads(raw) if raw else {}
                    except (ValueError, UnicodeError):
                        status, payload = 400, {"error": "Malformed JSON"}
                    else:
                        status, payload, extra = service.handle(method, path,
                            {k: v[-1] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}, body, headers)
                else:
                    status, payload, extra = service.handle(method, path,
                        {k: v[-1] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}, body, headers)
        except Exception:
            import logging
            logging.exception("Request failed")
            status, payload = 500, {"error": "Internal error; see the local application log"}
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, allow_nan=False).encode()
            extra.setdefault("Content-Type", "application/json")
        extra.update({"Content-Length": str(len(payload)), "Cache-Control": "no-store",
                      "X-Content-Type-Options": "nosniff"})
        start_response(f"{status} {HTTPStatus(status).phrase}", list(extra.items()))
        return [payload]
    return application
