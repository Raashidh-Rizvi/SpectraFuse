FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/*.py ./backend/
COPY backend/agents/ ./backend/agents/
COPY docs/PROJECT_REFERENCE.md ./docs/PROJECT_REFERENCE.md
COPY README.md SUBMISSION.md ./
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --system --no-create-home spectrafuse
USER spectrafuse
EXPOSE 8001
# Run exactly one worker: chat session memory lives in process (see the hosting guide).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/fire/chat/health', timeout=4)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
