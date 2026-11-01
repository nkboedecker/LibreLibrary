# The Docker phase of the project plan adds configurable UID and GID.
FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913 AS build
RUN pip install --no-cache-dir uv==0.13.6
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913
LABEL org.opencontainers.image.title="LibreLibrary" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN useradd --uid 1000 --no-create-home librelibrary \
    && install -d -o 1000 -g 1000 /data
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY migrations ./migrations
USER 1000
ENV PATH="/app/.venv/bin:$PATH" \
    LIBRELIBRARY_DATABASE_URL="sqlite:////data/librelibrary.db"
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"]
# The app reads forwarded headers itself, and only from LIBRELIBRARY_TRUSTED_PROXIES.
CMD ["uvicorn", "librelibrary.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
