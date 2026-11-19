#!/usr/bin/env bash
# Build and run the NexCoder agent CLI container (issue #115).
#
#   scripts/agent-cli.sh build            build the image
#   scripts/agent-cli.sh login            log in with your own account (stored in a named volume)
#   scripts/agent-cli.sh check            check that the CLI inside the image works
#   scripts/agent-cli.sh up | down        start or stop the long-running container (exec mode)
#   scripts/agent-cli.sh dispatch "task"  send one task through ContainerCLIBackend
#
# Environment: NEXCODER_CONTAINER_RUNTIME (docker or podman), NEXCODER_AGENT_IMAGE,
# NEXCODER_AGENT_VOLUME, NEXCODER_AGENT_CLI (claude or generic).
# Use only with your own login and within the CLI provider's terms of use.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${NEXCODER_CONTAINER_RUNTIME:-docker}"
IMAGE="${NEXCODER_AGENT_IMAGE:-nexcoder/agent-cli:local}"
VOLUME="${NEXCODER_AGENT_VOLUME:-nexcoder-agent-cli-home}"
CLI="${NEXCODER_AGENT_CLI:-claude}"
CONTEXT="$ROOT/docker/agent-cli"
PYTHON="${PYTHON:-python3}"

action="${1:-help}"
shift || true

case "$action" in
  build)
    "$RUNTIME" build -t "$IMAGE" "$CONTEXT"
    ;;
  login)
    "$RUNTIME" volume create "$VOLUME" >/dev/null
    "$RUNTIME" run --rm -it -e "NEXCODER_AGENT_CLI=$CLI" -v "$VOLUME:/home/agent" "$IMAGE" login
    ;;
  check)
    "$RUNTIME" run --rm -e "NEXCODER_AGENT_CLI=$CLI" -v "$VOLUME:/home/agent" "$IMAGE" check
    ;;
  up)
    "$RUNTIME" compose -f "$CONTEXT/compose.yml" up -d --build
    ;;
  down)
    "$RUNTIME" compose -f "$CONTEXT/compose.yml" down
    ;;
  dispatch)
    if [ "$#" -lt 1 ]; then
      echo "usage: $0 dispatch \"task text\" [extra nexcoder-agents dispatch options]" >&2
      exit 2
    fi
    "$PYTHON" -m nexcoder_agents.cli dispatch --backend container --runtime "$RUNTIME" --image "$IMAGE" \
      --volume "$VOLUME" --cli "$CLI" "$@"
    ;;
  *)
    sed -n '2,12p' "$0"
    ;;
esac
