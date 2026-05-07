FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 安装 git：因为 requirements.txt 里有 git+https 依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY . /app

CMD ["python", "main.py"]