// Default runtime config — overwritten by docker-entrypoint.sh inside the container.
// During local development (pnpm start) this file is served as-is.
window.__ENV__ = {
  API_PREFIX: "http://127.0.0.1:8000"
};
