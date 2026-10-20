FROM python:3.12-slim-bookworm
WORKDIR /arena
RUN pip install --no-cache-dir uv==0.13.1
COPY backend/pyproject.toml backend/uv.lock backend/.python-version /arena/backend/
RUN uv sync --project backend --frozen --no-dev --python /usr/local/bin/python --no-python-downloads
COPY contracts /arena/contracts
COPY architecture.md /arena/architecture.md
COPY backend/app /arena/backend/app
COPY backend/migrations /arena/backend/migrations
COPY backend/alembic.ini /arena/backend/alembic.ini
ENV PATH="/arena/backend/.venv/bin:$PATH"
WORKDIR /arena/backend
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
