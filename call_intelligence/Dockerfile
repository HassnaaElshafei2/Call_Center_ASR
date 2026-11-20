# The web app and the worker (same image). Build from call_intelligence/:
#   docker build -t sia-callintel .
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./
COPY demo_data/ /app/demo_data/
COPY --from=web /web/dist /app/frontend/dist
ENV FRONTEND_DIR=/app/frontend/dist STORAGE_DIR=/data/recordings
EXPOSE 8000
CMD ["sh", "-c", "python -m callintel.manage init && uvicorn callintel.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
