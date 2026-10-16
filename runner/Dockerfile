FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/ottv2-runner
COPY pyproject.toml README.md ./
COPY ottv2_runner ./ottv2_runner
RUN python -m pip install --no-cache-dir .

CMD ["ottv2-runner-worker", "--queue", "build"]
