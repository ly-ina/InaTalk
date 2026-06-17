# ============================================
# 轻聊 InaTalk · 容器镜像
# 构建: docker build -t ruanks:latest .
# ============================================
FROM python:3.13-slim

LABEL app="ruanks" \
      description="轻聊 InaTalk"

WORKDIR /app

# 使用清华 pip 镜像加速
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY src/ ./src/
COPY static/ ./static/

RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8766

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:${PORT:-8766}/api/health').raise_for_status()"

CMD ["python", "main.py"]
