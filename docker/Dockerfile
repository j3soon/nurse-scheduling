FROM python:3.12

WORKDIR /app

# Common Tools
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    gnupg \
    iputils-ping \
    jq \
    ripgrep \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY core/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

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

# Ref: https://github.com/j3soon/dockerfile-fragments/blob/main/codex/Dockerfile
# Install Codex CLI
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
RUN apt-get update && apt-get install -y \
    nodejs \
    && rm -rf /var/lib/apt/lists/*
# This remote metadata changes when the npm latest tag advances, which
# invalidates the install layer during normal Docker builds.
ADD https://registry.npmjs.org/@openai%2Fcodex/latest /tmp/openai-codex-latest.json
RUN npm install -g @openai/codex
RUN codex_version="$(codex --version)" \
    && test -n "$codex_version" \
    && echo "Installed Codex CLI: $codex_version"

# Ref: https://github.com/j3soon/dockerfile-fragments/blob/main/opencode/Dockerfile
# Install OpenCode CLI
ADD https://api.github.com/repos/anomalyco/opencode/releases/latest /tmp/opencode-latest-release.json
ENV PATH="/root/.opencode/bin:${PATH}"
RUN curl -fsSL https://opencode.ai/install | bash
RUN opencode_version="$(opencode --version)" \
    && test -n "$opencode_version" \
    && echo "Installed OpenCode CLI: $opencode_version"

WORKDIR /app

ENTRYPOINT ["/bin/bash"]
