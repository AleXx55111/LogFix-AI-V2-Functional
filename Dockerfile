FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
WORKDIR /app
COPY backend/requirements.txt backend/requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY backend/app ./backend/app
COPY backend/__init__.py ./backend/__init__.py
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN useradd --system --uid 10001 logfix && chown -R logfix:logfix /app
USER logfix
EXPOSE 10000
CMD ["sh","-c","uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
