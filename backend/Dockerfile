# Python 3.12, not 3.13: the rendering stack added in later milestones
# (manim, moviepy) is only reliably packaged for 3.12.
FROM python:3.12-slim

WORKDIR /app

# Kept minimal on purpose. ffmpeg and a LaTeX distribution get added in the
# milestone that actually renders video -- adding them now would mean waiting
# on a 2 GB image build to test a PDF upload.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p storage/uploads

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
