FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.5.*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY common ./common
COPY app ./app

ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8080"]
