# syntax=docker/dockerfile:1.4
FROM node:lts-alpine AS node_builder

WORKDIR /app
COPY frontend ./
ENV NODE_ENV=production
RUN if [ ! -f "/app/exported/index.html" ]; then \
  npm install -g pnpm && \
  NODE_ENV=production pnpm install --frozen-lockfile --prod --ignore-scripts && \
  pnpm run generate; \
  else echo "Skipping UI build, already built."; fi

FROM python:3.13-bookworm AS python_builder

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1
ENV PIP_NO_CACHE_DIR=off
ENV PIP_CACHE_DIR=/root/.cache/pip
ENV UV_CACHE_DIR=/root/.cache/uv
ENV DEBIAN_FRONTEND=noninteractive
ENV UV_INSTALL_DIR=/usr/bin

COPY --from=astral/uv:latest /uv /usr/bin/

WORKDIR /opt/

COPY ./pyproject.toml ./uv.lock ./
RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
  --mount=type=cache,target=/root/.cache/uv,id=uv-cache \
  uv venv --system-site-packages --relocatable ./python && \
  VIRTUAL_ENV=/opt/python uv sync --no-dev --link-mode=copy --active

FROM python:3.13-slim

ARG TZ=UTC
ARG USER_ID=1000
ENV IN_CONTAINER=1
ENV UMASK=0002
ENV FBC_CONFIG_PATH=/config
ENV FBC_STORAGE_PATH=/downloads
ENV FBC_FRONTEND_EXPORT_PATH=/app/frontend/exported
ENV PYDEVD_DISABLE_FILE_VALIDATION=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1
ENV FBC_DEV_MODE=0

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
  apt-get install -y --no-install-recommends libmagic1 && \
  rm -rf /var/lib/apt/lists/*

RUN mkdir /config /downloads && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone && \
  useradd -u ${USER_ID:-1000} -U -d /app -s /bin/bash app && \
  chown -R app:app /config /downloads

COPY --chown=app:app ./alembic.ini /app/alembic.ini
COPY --chown=app:app ./backend /app/backend
COPY --chown=app:app --from=node_builder /app/exported /app/frontend/exported
COPY --chown=app:app --from=python_builder /opt/python /opt/python
COPY --from=ghcr.io/arabcoders/jellyfin-ffmpeg /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=ghcr.io/arabcoders/jellyfin-ffmpeg /usr/bin/ffprobe /usr/bin/ffprobe

# Install fbc CLI script
COPY ./backend/bin/fbc /usr/bin/fbc
RUN chmod +x /usr/bin/fbc

ENV PATH="/opt/python/bin:$PATH"

VOLUME /config
VOLUME /downloads

EXPOSE 8000

USER app

WORKDIR /tmp

CMD ["/opt/python/bin/python", "/app/backend/main.py"]
