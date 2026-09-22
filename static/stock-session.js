/* Preserve an existing app login during the stock-only migration. */
"use strict";
window.StockSession = (() => {
  let memoryToken = "";
  return {
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
