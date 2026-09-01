FROM e2bdev/base:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        diffutils \
        grep \
        python3-minimal \
        ripgrep \
        sed \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir 'ruamel.yaml==0.19.1'

RUN mkdir -p /workspace /reference \
    && chown -R user:user /workspace /reference

USER user
WORKDIR /workspace
