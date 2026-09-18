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

RUN python3 -m pip install --no-cache-dir \
        'openpyxl==3.1.5' \
        'defusedxml==0.7.1' \
        'Pillow==12.3.0' \
        'pypdf==6.19.0' \
        'pypdfium2==5.13.0' \
        'ruamel.yaml==0.19.1'

RUN mkdir -p /workspace /reference/tools \
    && chown -R user:user /workspace /reference

USER user
WORKDIR /workspace
