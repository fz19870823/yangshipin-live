# CMG 解密 HLS 推流服务器
# 央视频直播解密 + 本地 HLS 推流
#
# docker compose up -d
# 访问 http://localhost:8080

FROM python:3.11-slim-bookworm

# Playwright 需要的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    libx11-xcb1 libxcb-dri3-0 libxshmfence1 libgl1 \
    ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装 Python 依赖（缓存友好）
RUN pip install --no-cache-dir \
    playwright==1.49.* \
    aiohttp==3.9.*

# 安装 Playwright Chromium 及依赖
RUN python -m playwright install --with-deps chromium

# 复制项目
COPY yangshipin/ ./yangshipin/
COPY server/ ./server/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

RUN mkdir -p /app/live_output

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8080/api/health || exit 1

CMD ["python", "-m", "server.app"]
