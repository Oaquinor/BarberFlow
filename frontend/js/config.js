/* Resolve the local split frontend/backend development setup. */
(function configureApiRoot() {
  const current = window.KINGFLOW_CONFIG || {};
  const isLocalFrontendServer = window.location.port === '3000'
    && ['localhost', '127.0.0.1'].includes(window.location.hostname);
  const localBackend = `${window.location.protocol}//${window.location.hostname}:8000`;
  window.KINGFLOW_CONFIG = {
    ...current,
    apiBaseUrl: current.apiBaseUrl || (isLocalFrontendServer ? localBackend : window.location.origin),
  };
})();
