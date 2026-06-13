FROM node:22-bookworm-slim AS frontend

WORKDIR /src/frontend

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable \
    && corepack prepare pnpm@9.15.4 --activate \
    && pnpm install --frozen-lockfile

COPY frontend/ ./

ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

RUN pnpm build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend /app/backend
COPY --from=frontend /src/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY start-backend.sh /app/start-backend.sh

RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && cd /app/backend \
    && python -m unittest discover -s tests \
    && chmod +x /app/start-backend.sh

EXPOSE 8080

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
