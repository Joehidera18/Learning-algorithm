"""Attach /strategy-lab pages and APIs without rewriting the main router."""


class _OfflineLab:
    def shutdown(self):
        return

    def status(self):
        return {"jobs": [], "catalog": {"strategies": [], "equity": {"providers": {}},
                                        "scope": "Strategy lab unavailable on this process."},
                "running": False, "error": self.message}

    def start(self, request):
        raise RuntimeError(self.message)

    def get(self, job_id):
        raise ValueError(self.message)

    def __init__(self, message):
        self.message = message


def attach(service):
    try:
        from .strategy_jobs import StrategyLabJobs
        service.strategy_lab = StrategyLabJobs(service.data_dir)
        service.strategy_lab.resume()
    except Exception as exc:
        service.strategy_lab = _OfflineLab("Strategy lab did not start: %s" % exc)
    original = service.handle

    def handle(method, path, query=None, body=None, headers=None):
        routed = route(service, method, path, query or {}, body)
        if routed is not None:
            return routed
        return original(method, path, query, body, headers)

    service.handle = handle


def route(service, method, path, query, body):
    if method == "GET" and path in ("/strategy-lab", "/strategy-lab/"):
        page = service.base_dir / "templates/strategy-lab.html"
        if not page.exists():
            return 404, {"error": "Strategy lab page missing"}, {}
        return 200, page.read_bytes(), {"Content-Type": "text/html; charset=utf-8"}
    if method == "GET" and path == "/static/strategy-lab.js":
        asset = service.base_dir / "static/strategy-lab.js"
        if not asset.exists():
            return 404, {"error": "Strategy lab script missing"}, {}
        return 200, asset.read_bytes(), {"Content-Type": "application/javascript; charset=utf-8"}
    if not path.startswith("/api/strategy-lab/"):
        return None
    action = path.removeprefix("/api/strategy-lab/")
    try:
        if action == "status" and method == "GET":
            payload = service.strategy_lab.status()
            for job in payload.get("jobs") or []:
                if job.get("status") == "complete" and hasattr(service.strategy_lab, "get"):
                    try:
                        job["result"] = service.strategy_lab.get(job["id"]).get("result")
                    except Exception:
                        job["result"] = None
            return 200, payload, {}
        if action == "start" and method == "POST":
            return 202, service.strategy_lab.start(body or {}), {}
        if action == "export" and method == "GET":
            import json
            job = service.strategy_lab.get(query.get("id"))
            return 200, json.dumps(job, indent=2, allow_nan=False).encode(), {
                "Content-Type": "application/json",
                "Content-Disposition": 'attachment; filename="strategy-lab.json"'}
        return 404, {"error": "Strategy lab route not found"}, {}
    except (ValueError, TypeError) as exc:
        return 400, {"error": str(exc)}, {}
    except RuntimeError as exc:
        return 409, {"error": str(exc)}, {}
