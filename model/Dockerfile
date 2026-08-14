ARG BASE_IMAGE_REGISTRY=docker.io/library
FROM ${BASE_IMAGE_REGISTRY}/python:3.12-slim
ARG DEBIAN_MIRROR=http://deb.debian.org
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
WORKDIR /app

RUN sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 先装 CPU 版 torch(避免 PyPI 默认捆绑 CUDA 使镜像膨胀约 3GB),再装其余依赖
RUN pip install --no-cache-dir torch --index-url "${PYTORCH_INDEX_URL}" \
    && pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY . .

RUN mkdir -p data model_cache logs chroma_db_unified

EXPOSE 8000

CMD ["python", "-m", "app.main"]
