# GhostShopper: API + demo store (+ dashboard build) in one container. Used by render.yaml.

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATABASE_PATH=/app/data/ghostshopper.db
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
# Chromium is only needed for BROWSER_PROVIDER=local; with Kernel the browser runs remotely.
RUN pip install --no-cache-dir -r backend/requirements.txt \
 && python -m playwright install --with-deps chromium
COPY pyproject.toml ./
COPY store/ store/
COPY backend/ backend/
COPY --from=frontend /app/frontend/dist frontend/dist
EXPOSE 8000
# Render sets PORT. One worker: runs are serialized by an in-process lock.
CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
