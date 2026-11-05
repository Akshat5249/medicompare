FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.11.21 && apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 && useradd --create-home --uid 10001 app
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# Build tools are not needed at runtime, so they are not shipped.
RUN pip uninstall -y uv setuptools
COPY --chown=10001 backend/ ./
COPY --chown=10001 data/ /srv/data/
USER app
EXPOSE 8000
# Forwarded addresses are trusted because the backend is reachable only from the private network (D20).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]
