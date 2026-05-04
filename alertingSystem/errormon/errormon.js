/**
 * errormon.js — Browser error monitoring client for the alerting-service API.
 *
 * Usage (script tag):
 *   <script src="errormon.js"></script>
 *   <script>
 *     const monitor = new Errormon({ apiUrl: "http://your-api:5001", serviceName: "my-app" });
 *     monitor.install(); // auto-capture window errors + unhandled rejections
 *   </script>
 *
 * Usage (ES module):
 *   import Errormon from "./errormon.js";
 *   const monitor = new Errormon({ apiUrl: "...", serviceName: "my-app" });
 *   monitor.install();
 *
 * Manual reporting inside try/catch:
 *   try { ... } catch (err) { monitor.catchError(err, { userId: "123" }); }
 *
 * Config options:
 *   apiUrl      (required) Base URL of the alerting-service API, no trailing slash.
 *   serviceName           Name shown in alert emails. Default: window.location.hostname
 *   environment           "production" | "staging" | "development". Default: "production"
 *   apiKey                Optional — only set if your server requires X-API-Key.
 *                         WARNING: this value is visible in browser DevTools. Prefer
 *                         leaving auth disabled or proxying through your own backend.
 */

(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    root.Errormon = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var MAX_RETRIES = 2;
  var RETRY_DELAY_MS = 1000;

  function Errormon(config) {
    if (!config || !config.apiUrl) {
      throw new Error("Errormon: apiUrl is required.");
    }
    this._apiUrl = config.apiUrl.replace(/\/$/, "") + "/errors";
    this._serviceName = config.serviceName || (typeof window !== "undefined" ? window.location.hostname : "frontend");
    this._environment = config.environment || "production";
    this._apiKey = config.apiKey || null;
    this._installed = false;
  }

  /**
   * Auto-attach global error handlers. Call once at app startup.
   * Safe to call multiple times — installs only once.
   */
  Errormon.prototype.install = function () {
    if (this._installed || typeof window === "undefined") return;
    this._installed = true;

    var self = this;

    window.addEventListener("error", function (event) {
      var err = event.error  || new Error(event.message || "Unknown error");
      self.catchError(err, {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      });
    });

    window.addEventListener("unhandledrejection", function (event) {
      var reason = event.reason;
      var err = reason instanceof Error ? reason : new Error(String(reason));
      self.catchError(err, { type: "unhandledrejection" });
    });
  };

  /**
   * Manually report an error (use inside try/catch blocks).
   * @param {Error|string} error
   * @param {Object}       metadata  Any extra key/value pairs to attach.
   */
  Errormon.prototype.catchError = function (error, metadata) {
    var err = error instanceof Error ? error : new Error(String(error));
    var payload = {
      error_type: err.name || "Error",
      error_message: err.message || String(err),
      stack_trace: err.stack || "(no stack trace)",
      timestamp: new Date().toISOString(),
      service_name: this._serviceName,
      environment: this._environment,
      metadata: Object.assign({ user_agent: _userAgent(), url: _currentUrl() }, metadata || {}),
    };
    this._sendWithRetry(payload, MAX_RETRIES);
  };

  Errormon.prototype._sendWithRetry = function (payload, retriesLeft) {
    var self = this;
    var headers = { "Content-Type": "application/json" };
    if (this._apiKey) headers["X-API-Key"] = this._apiKey;

    fetch(this._apiUrl, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload),
      keepalive: true,
    }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
    }).catch(function (err) {
      if (retriesLeft > 0) {
        setTimeout(function () {
          self._sendWithRetry(payload, retriesLeft - 1);
        }, RETRY_DELAY_MS);
      } else {
        console.warn("Errormon: failed to report error —", err.message);
      }
    });
  };

  function _userAgent() {
    return typeof navigator !== "undefined" ? navigator.userAgent : "";
  }

  function _currentUrl() {
    return typeof window !== "undefined" ? window.location.href : "";
  }

  return Errormon;
});
