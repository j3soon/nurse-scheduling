FROM python:3.12

WORKDIR /app

# Common Tools
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    ripgrep \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY core/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Ref: https://github.com/j3soon/dockerfile-fragments/blob/main/codex/Dockerfile
# Install Codex CLI
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
RUN apt-get update && apt-get install -y \
    nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @openai/codex

# Install Bun
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# Install the frontend's locked Playwright version and bake browser binaries into
# a stable image path so they survive `docker run --rm` sessions.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY web-frontend/package.json web-frontend/bun.lock /tmp/web-frontend/
WORKDIR /tmp/web-frontend
RUN bun install --frozen-lockfile
RUN bunx playwright install --with-deps chromium

WORKDIR /app

ENTRYPOINT ["/bin/bash"]
