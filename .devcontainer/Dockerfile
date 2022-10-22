ARG VARIANT="3.10-bullseye"
FROM mcr.microsoft.com/vscode/devcontainers/python:0-${VARIANT}

ARG NODE_VERSION="none"
RUN if [ "${NODE_VERSION}" != "none" ]; then su vscode -c "umask 0002 && . /usr/local/share/nvm/nvm.sh && nvm install ${NODE_VERSION} 2>&1"; fi

COPY ./install.sh /tmp/deps/install.sh
COPY ./pyproject.toml /tmp/deps/pyproject.toml

RUN bash /tmp/deps/install.sh "sudo" \
    && sudo apt-get -y update \
    && sudo apt-get -y install graphviz \
    && python3 -m pip install --upgrade pip \
    && python3 -m pip install --upgrade --disable-pip-version-check --no-cache-dir -e "/tmp/deps[tests]" \
    && rm -rf /tmp/deps