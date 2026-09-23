"""Shared WSGI JSON transport, independent of any asset class or broker."""
import json
import gzip


def wsgi_application(service):
    from urllib.parse import parse_qs
    from http import HTTPStatus

    def application(environ, start_response):
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        body = None
        headers = {"content-type": environ.get("CONTENT_TYPE", ""),
                   "authorization": environ.get("HTTP_AUTHORIZATION", ""),
                   "if-none-match": environ.get("HTTP_IF_NONE_MATCH", "")}
        extra = {}
        try:
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
            except (TypeError, ValueError):
                length = -1
            if length < 0:
                status, payload = 400, {"error": "Invalid request length"}
            elif length > 32768:
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
            payload = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
            extra.setdefault("Content-Type", "application/json")
        accepted = []
        for item in environ.get("HTTP_ACCEPT_ENCODING", "").split(","):
            parts = [part.strip() for part in item.split(";")]
            if parts[0].lower() == "gzip":
                try:
                    quality = next((float(p.split("=",1)[1]) for p in parts[1:] if p.startswith("q=")), 1.)
                except ValueError:
                    quality = 0.
                if quality > 0:
                    accepted.append("gzip")
        compressible = extra.get("Content-Type", "").split(";")[0] in (
            "application/json", "application/javascript", "text/css", "text/html")
        if compressible:
            extra["Vary"] = "Accept-Encoding"
        if status == 200 and compressible and len(payload) >= 1024 and "gzip" in accepted:
            payload = gzip.compress(payload, compresslevel=1, mtime=0)
            extra["Content-Encoding"] = "gzip"
        extra.setdefault("Cache-Control", "no-store")
        if status != 304:
            extra["Content-Length"] = str(len(payload))
        extra["X-Content-Type-Options"] = "nosniff"
        start_response(f"{status} {HTTPStatus(status).phrase}", list(extra.items()))
        return [payload]
    return application
