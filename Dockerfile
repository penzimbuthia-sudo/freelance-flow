# syntax=docker/dockerfile:1
# Official multi-arch image digests verified from Docker Hub; update deliberately.
FROM node:22-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.14-slim-bookworm@sha256:3fe1a0b6c2d6b2ebb572906cdabeca75aeb558c0c17db5ffefbcf8094871c32b AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production FLASK_SKIP_DOTENV=1
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.lock \
    && useradd --create-home --uid 10001 appuser
COPY backend ./backend
COPY wsgi.py gunicorn.conf.py ./
COPY --from=frontend /build/dist ./dist
USER appuser
EXPOSE 10000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
