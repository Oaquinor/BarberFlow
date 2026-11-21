"use strict";

(function () {
  function trustedWhatsAppShareUrl(value) {
    try {
      const url = new URL(value);
      return url.origin === "https://wa.me" && !url.username && !url.password
        ? url.href
        : null;
    } catch (_) {
      return null;
    }
  }

  window.KingFlowSecurity = Object.freeze({ trustedWhatsAppShareUrl });
})();
