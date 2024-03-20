FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-calc bubblewrap util-linux fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 verifier
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN pip install . && mkdir /app/data && chown -R verifier:verifier /app
USER verifier
EXPOSE 8000 8501
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
