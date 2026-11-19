# NexCoder agent CLI backend image (issue #115).
#
# Contains an agent CLI (Claude Code by default) and a headless entrypoint that
# reads one JSON task on stdin and prints one JSON result on stdout.
#
# No credential is ever copied into this image. The user logs in once with
# `nexcoder-agent login`, and the CLI keeps that login in /home/agent, which is a
# named volume mounted at run time (see README.md in this folder).
FROM node:22-bookworm-slim

ARG CLAUDE_CODE_PACKAGE=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates git tini \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "${CLAUDE_CODE_PACKAGE}@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

RUN groupadd --system agent \
    && useradd --system --gid agent --create-home --home-dir /home/agent --shell /usr/sbin/nologin agent \
    && mkdir -p /workspace \
    && chown agent:agent /workspace

COPY --chmod=0755 entrypoint.py /usr/local/bin/nexcoder-agent

ENV HOME=/home/agent \
    NEXCODER_AGENT_CLI=claude \
    DISABLE_AUTOUPDATER=1 \
    PYTHONDONTWRITEBYTECODE=1

USER agent
WORKDIR /workspace
VOLUME ["/home/agent"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/nexcoder-agent"]
CMD ["check"]
