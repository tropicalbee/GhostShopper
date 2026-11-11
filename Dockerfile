# GhostShopper: API + demo store (+ dashboard build) in one container. Used by render.yaml.

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# DEV_OPTIONS=0 fails closed: the deployed image keeps developer options and the open settings page off by default.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATABASE_PATH=/app/data/ghostshopper.db \
    DEV_OPTIONS=0
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
# Chromium is only needed for BROWSER_PROVIDER=local (build with --build-arg INSTALL_CHROMIUM=1); render.yaml uses Kernel.
ARG INSTALL_CHROMIUM=0
RUN pip install --no-cache-dir -r backend/requirements.txt \
 && if [ "$INSTALL_CHROMIUM" = "1" ]; then python -m playwright install --with-deps chromium; fi
COPY pyproject.toml ./
COPY store/ store/
COPY backend/ backend/
COPY --from=frontend /app/frontend/dist frontend/dist
# Run as a normal user; /app/data (the SQLite file) and /app/runs (screenshots) are the only writable places.
RUN useradd --system --create-home --uid 10001 app \
 && mkdir -p /app/data /app/runs \
 && chown -R app:app /app/data /app/runs \
 && if [ -d /ms-playwright ]; then chmod -R a+rX /ms-playwright; fi
USER app
EXPOSE 8000
# Render sets PORT. One worker: runs are serialized by an in-process lock and the rate limiter is in memory.
# Proxy headers only give uvicorn the https scheme. Rate limits do not use the rewritten client address: they read
# X-Forwarded-For from the right (TRUSTED_PROXY_HOPS entries in), because the left entries are chosen by the client.
CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
