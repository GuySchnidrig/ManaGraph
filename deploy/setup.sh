#!/usr/bin/env bash
# One-time setup of a public ManaGraph SPARQL endpoint on a fresh Ubuntu server
# (written for Oracle Cloud Always Free, Ampere A1, Ubuntu 24.04; works on any
# Ubuntu host with ~12 GB RAM, since the pipeline peaks at ~9 GB).
#
#   curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh | bash
#   # or, with your own domain pointing at the server:
#   curl -fsSL .../deploy/setup.sh | bash -s -- sparql.example.org
#
# Run it as the default user (ubuntu), not root. It installs Docker and uv,
# opens ports 80/443, clones the repo, starts Caddy for HTTPS, installs a
# weekly rebuild timer and runs the first build. Without a domain it uses
# <ip>.sslip.io, a free wildcard DNS name that resolves to the server's IP.
set -euo pipefail

REPO=https://github.com/GuySchnidrig/ManaGraph.git
DIR="$HOME/ManaGraph"

if [[ $EUID -eq 0 ]]; then
  echo "Run as a normal user with sudo, not as root." >&2
  exit 1
fi

echo "== packages =="
sudo apt-get update -q
sudo apt-get install -yq docker.io git curl iptables-persistent
sudo usermod -aG docker "$USER"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "== firewall =="
# Oracle's Ubuntu images reject everything but SSH in iptables, on top of the
# VCN security list (open 80 and 443 there too, see deploy/README.md).
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
done
sudo netfilter-persistent save

echo "== repository =="
if [[ -d "$DIR/.git" ]]; then git -C "$DIR" pull --ff-only; else git clone "$REPO" "$DIR"; fi

echo "== access token =="
TOKEN_FILE="$HOME/.managraph-token"
[[ -f "$TOKEN_FILE" ]] || (umask 077 && head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$TOKEN_FILE")

echo "== https =="
SITE="${1:-$(curl -fsS https://checkip.amazonaws.com | tr . -).sslip.io}"
echo "$SITE" > "$HOME/.managraph-site"
sudo docker rm -f caddy 2>/dev/null || true
sudo docker run -d --name caddy --restart unless-stopped --network host \
  -e SITE="$SITE" \
  -v "$DIR/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v caddy_data:/data -v caddy_config:/config \
  docker.io/library/caddy:2

echo "== weekly rebuild =="
sed "s|@USER@|$USER|g; s|@DIR@|$DIR|g" "$DIR/deploy/managraph-update.service" \
  | sudo tee /etc/systemd/system/managraph-update.service >/dev/null
sudo cp "$DIR/deploy/managraph-update.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now managraph-update.timer

echo "== first build (a few minutes) =="
# sg runs it with the new docker group, without logging out and back in.
sg docker -c "bash '$DIR/deploy/update.sh'"

echo
echo "SPARQL endpoint: https://$SITE/"
echo "Access token (for privileged QLever commands): $TOKEN_FILE"
