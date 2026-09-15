FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY adr_gateway ./adr_gateway
COPY config/docker.toml ./config/gateway.toml

FROM base AS test
COPY tests ./tests
RUN python -m pytest -q -p no:cacheprovider tests

FROM base AS runtime
ENV RT_GATEWAY_HOST=0.0.0.0 RT_GATEWAY_STORAGE_ROOT=/data
EXPOSE 18081
CMD ["python", "-m", "adr_gateway"]
