# Build Aria2 without BitTorrent and Metalink support.
FROM python:3.12-slim-bookworm AS aria2-build
ARG ARIA2_VERSION=1.37.0
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential autoconf automake autopoint libtool pkg-config curl ca-certificates \
    libssl-dev libxml2-dev zlib1g-dev libsqlite3-dev \
    libssh2-1-dev libexpat1-dev libc-ares-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/build
RUN curl -fsSLO "https://github.com/aria2/aria2/releases/download/release-${ARIA2_VERSION}/aria2-${ARIA2_VERSION}.tar.xz" \
    && tar -xf "aria2-${ARIA2_VERSION}.tar.xz" \
    && cd "aria2-${ARIA2_VERSION}" \
    && ./configure --prefix=/usr/local --disable-bittorrent --disable-metalink \
       --enable-shared=no --with-openssl --without-gnutls \
    && make -j"$(nproc)" \
    && make install \
    && aria2c --version | tee /tmp/aria2-version \
    && ! grep -Eiq "BitTorrent|Metalink" /tmp/aria2-version

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL=/usr/local
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential ffmpeg p7zip-full file tini procps \
    libmagic1 libssl3 libxml2 zlib1g libsqlite3-0 libssh2-1 libexpat1 \
    libc-ares2 libattr1-dev && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deno.land/install.sh | sh \
    && /usr/local/bin/deno --version
COPY --from=aria2-build /usr/local/bin/aria2c /usr/local/bin/aria2c
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
COPY . .
RUN chmod +x start.sh aria2-start.sh && mkdir -p /app/downloads
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "start.sh"]
