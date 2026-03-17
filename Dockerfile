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

# Install Playwright Chromium browser and system dependencies so browser E2E tests
# can run inside the development image without extra manual setup.
RUN bunx playwright install --with-deps chromium

ENTRYPOINT ["/bin/bash"]
