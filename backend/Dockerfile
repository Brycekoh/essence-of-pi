# The API server, for docker compose.
#
# It renders nothing itself. It starts render, ffmpeg and speech containers on
# the host's Docker daemon through a mounted socket, so it needs the docker
# *CLI* -- copied as a single static binary -- and not a daemon of its own.
FROM python:3.12-slim

COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Storage lives in a named volume mounted at /data, so sandboxes can be handed
# sub-directories of it. See app/services/container.py.
ENV STORAGE_ROOT=/data \
    UPLOAD_DIR=/data/uploads \
    VIDEOS_DIR=/data/videos

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s \
  CMD curl -fsS http://localhost:8000/health || exit 1

# One worker, deliberately: jobs live in this process's memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
