ARG BASE_IMAGE_REGISTRY=docker.io/library
FROM ${BASE_IMAGE_REGISTRY}/python:3.12-slim
ARG DEBIAN_MIRROR=http://deb.debian.org
ARG PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /app

RUN sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
# uv + 锁文件: 完全可复现构建(requirements.lock 由 uv pip compile 生成)
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache --index-url "${PIP_INDEX_URL}" -r requirements.lock

COPY . .

RUN mkdir -p data model_cache logs chroma_db_unified

EXPOSE 8000

CMD ["python", "-m", "app.main"]
