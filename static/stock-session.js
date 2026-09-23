/* Preserve an existing app login during the stock-only migration. */
"use strict";
window.StockSession = (() => {
  let memoryToken = "";
  async function request(url, options = {}, type = "json", timeoutMs = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {...options, credentials:"same-origin", signal:controller.signal});
      if (!response.ok) {
        let message = "Request failed (" + response.status + ")";
        try { message = (await response.json()).error || message; } catch (_) {}
        const error = Error(message); error.status = response.status; throw error;
      }
      return await (type === "blob" ? response.blob() : response.json());
    } catch (error) {
      if (controller.signal.aborted) throw Error("Request timed out. Refresh to check its status before submitting again.");
      throw error;
    } finally { clearTimeout(timer); }
  }
  // Schedule after completion so slow responses cannot build a polling backlog.
  function poll(refresh, busy, enabled = () => true) {
    let timer, running = false;
    async function tick() {
      clearTimeout(timer);
      if (running) return;
      running = true;
      try { if (!document.hidden && enabled()) await refresh(); }
      finally {
        running = false;
        timer = setTimeout(tick, busy() ? 8000 : 30000);
      }
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
    window.addEventListener("online", tick);
    tick();
  }
  return {
    request, poll,
    getToken() {
      try { return sessionStorage.getItem("stockAccessToken") || sessionStorage.getItem("cryptoAccessToken") || memoryToken; }
      catch (_) { return memoryToken; }
    },
    setToken(value) {
      memoryToken = value;
      try { sessionStorage.setItem("stockAccessToken", value); } catch (_) { /* Usable for this page visit. */ }
    }
  };
})();
