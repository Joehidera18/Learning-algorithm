"""Attach /strategy-lab pages and APIs without rewriting the main router."""

from .strategy_jobs import StrategyLabJobs


def attach(service):
    service.strategy_lab = StrategyLabJobs(service.data_dir)
    service.strategy_lab.resume()
    original = service.handle

    def handle(method, path, query=None, body=None, headers=None):
        routed = route(service, method, path, query or {}, body)
        if routed is not None:
            return routed
        return original(method, path, query, body, headers)

    service.handle = handle


def route(service, method, path, query, body):
    if method == "GET" and path in ("/strategy-lab", "/strategy-lab/"):
        return 200, (service.base_dir / "templates/strategy-lab.html").read_bytes(), {"Content-Type": "text/html; charset=utf-8"}
    if method == "GET" and path == "/static/strategy-lab.js":
        return 200, (service.base_dir / "static/strategy-lab.js").read_bytes(), {"Content-Type": "application/javascript; charset=utf-8"}
    if not path.startswith("/api/strategy-lab/"):
        return None
    action = path.removeprefix("/api/strategy-lab/")
    if action == "status" and method == "GET":
        payload = service.strategy_lab.status()
        for job in payload["jobs"]:
            if job["status"] == "complete":
                job["result"] = service.strategy_lab.get(job["id"]).get("result")
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
