#!/usr/bin/env bash
# One-time setup of a ManaGraph SPARQL endpoint on an Ubuntu server with 12 GB
# RAM or more (the pipeline peaks at ~9 GB; an 8 GB swap file covers the peak
# while QLever keeps serving during a rebuild).
#
#   setup.sh --tailscale          # homelab: HTTPS inside your tailnet only
#   setup.sh --funnel             # homelab: public HTTPS via Tailscale Funnel
#   setup.sh                      # cloud VM: public HTTPS on <ip>.sslip.io (Caddy)
#   setup.sh sparql.example.org   # cloud VM: public HTTPS on your own domain (Caddy)
#
# Fetch and run it in one go:
#   curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh | bash -s -- --tailscale
#
# If Tailscale runs in a Docker container rather than on the host, say how to
# reach it and, unless the container uses host networking, where QLever is:
#   TAILSCALE="docker exec tailscale tailscale" TS_TARGET=http://172.17.0.1:7019 setup.sh --tailscale
#
# Run it as a normal user with sudo, not root. It installs Docker (if missing)
# and uv, clones the repo, exposes QLever over HTTPS, installs a weekly rebuild
# timer and runs the first build.
set -euo pipefail

REPO=https://github.com/GuySchnidrig/ManaGraph.git
DIR="$HOME/ManaGraph"
MODE="${1:-}"
read -ra TS <<< "${TAILSCALE:-tailscale}"   # the tailscale CLI, possibly via docker exec
TS_TARGET="${TS_TARGET:-7019}"               # what Tailscale proxies to

if [[ $EUID -eq 0 ]]; then
  echo "Run as a normal user with sudo, not as root." >&2
  exit 1
fi
if [[ $MODE == --tailscale || $MODE == --funnel ]] && ! sudo "${TS[@]}" version >/dev/null 2>&1; then
  echo "Can't run '${TS[*]}'. Install Tailscale (https://tailscale.com/download/linux)," >&2
  echo "or, if it runs in a container, set TAILSCALE=\"docker exec <container> tailscale\"." >&2
  exit 1
fi

echo "== packages =="
sudo apt-get update -q
sudo apt-get install -yq git curl
# Keep an existing Docker (often docker-ce from Docker's own repo); docker.io
# would conflict with it.
command -v docker >/dev/null || sudo apt-get install -yq docker.io
sudo usermod -aG docker "$USER"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "== swap =="
if ! swapon --show | grep -q .; then
  sudo fallocate -l 8G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== repository =="
if [[ -d "$DIR/.git" ]]; then git -C "$DIR" pull --ff-only; else git clone "$REPO" "$DIR"; fi

echo "== access token =="
TOKEN_FILE="$HOME/.managraph-token"
[[ -f "$TOKEN_FILE" ]] || (umask 077 && head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$TOKEN_FILE")

echo "== weekly rebuild =="
sed "s|@USER@|$USER|g; s|@DIR@|$DIR|g" "$DIR/deploy/managraph-update.service" \
  | sudo tee /etc/systemd/system/managraph-update.service >/dev/null
sudo cp "$DIR/deploy/managraph-update.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now managraph-update.timer

echo "== first build (a few minutes) =="
# sg runs it with the new docker group, without logging out and back in.
sg docker -c "bash '$DIR/deploy/update.sh'"

echo "== https =="
case "$MODE" in
  --tailscale | --funnel)
    # Tailscale terminates HTTPS with a certificate for the machine's
    # MagicDNS name and proxies to QLever; nothing is opened on the router.
    if [[ $MODE == --funnel ]]; then
      sudo "${TS[@]}" funnel --bg "$TS_TARGET"
    else
      sudo "${TS[@]}" serve --bg "$TS_TARGET"
    fi
    SITE="$(sudo "${TS[@]}" status --json | python3 -c 'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
    ;;
  *)
    sudo apt-get install -yq iptables-persistent
    # Oracle's Ubuntu images reject everything but SSH in iptables, on top of
    # the VCN security list (open 80 and 443 there too, see deploy/README.md).
    for port in 80 443; do
      sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
        || sudo iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
    done
    sudo netfilter-persistent save
    SITE="${MODE:-$(curl -fsS https://checkip.amazonaws.com | tr . -).sslip.io}"
    sudo docker rm -f caddy 2>/dev/null || true
    sudo docker run -d --name caddy --restart unless-stopped --network host \
      -e SITE="$SITE" \
      -v "$DIR/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
      -v caddy_data:/data -v caddy_config:/config \
      docker.io/library/caddy:2
    ;;
esac
echo "$SITE" > "$HOME/.managraph-site"

echo
echo "SPARQL endpoint: https://$SITE/"
echo "Access token (for privileged QLever commands): $TOKEN_FILE"
