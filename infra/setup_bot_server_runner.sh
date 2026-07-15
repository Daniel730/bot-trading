#!/usr/bin/env bash
# Install/configure the GitHub Actions self-hosted runner on bot-server (x86_64).
# Usage (on bot-server):
#   REGISTRATION_TOKEN=XXXX ./setup_bot_server_runner.sh
set -euo pipefail

TOKEN="${REGISTRATION_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "REGISTRATION_TOKEN is required" >&2
  exit 1
fi

RUNNER_VERSION="${RUNNER_VERSION:-2.328.0}"
RUNNER_DIR="${HOME}/actions-runner"
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [[ ! -f ./config.sh ]]; then
  ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
  curl -fsSL -o "$ARCHIVE" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}"
  tar xzf "./${ARCHIVE}"
  rm -f "./${ARCHIVE}"
fi

if [[ ! -f .runner ]]; then
  ./config.sh --unattended \
    --url https://github.com/Daniel730/bot-trading \
    --token "$TOKEN" \
    --name bot-server-mini-pc \
    --labels bot-server \
    --work _work \
    --replace
else
  echo "RUNNER_ALREADY_CONFIGURED"
fi

if [[ ! -f .service ]]; then
  sudo ./svc.sh install
fi

sudo ./svc.sh start
sudo ./svc.sh status
echo "RUNNER_SETUP_OK"
