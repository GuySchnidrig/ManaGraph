# Deploying the endpoint

Scripts to run a ManaGraph SPARQL endpoint on one Ubuntu server. The server
builds the graph itself from Scryfall bulk data, QLever serves it, and a
systemd timer rebuilds it every week. The public endpoint at
<https://homelab.taila88e34.ts.net/> runs this way on a home server.

```
Scryfall bulk data ─► uv run managraph ─► qlever index ─► QLever :7019 ─► HTTPS ─► https://<site>/
                      └──────────── weekly: managraph-update.timer ────────────┘
```

HTTPS comes from one of two front ends:

| Front end | For | Address | Ports to open |
|---|---|---|---|
| **Tailscale** (`--tailscale`, `--funnel`) | a home server | `https://<machine>.<tailnet>.ts.net/` | none |
| **Caddy** (default) | a cloud VM with a public IP | `https://<ip>.sslip.io/` or your domain | 80, 443 |

## Requirements

- Ubuntu 22.04 or later, amd64 or arm64.
- 12 GB RAM or more. The pipeline peaks at about 9 GB while QLever keeps
  serving the old index; setup adds an 8 GB swap file if there is no swap.
- About 20 GB of disk for downloads, the Oxigraph store, the QLever index
  and Docker images.
- A normal user with sudo. The scripts refuse to run as root.

## Home server with Tailscale

The server has to be on your [tailnet](https://tailscale.com/kb/1136/tailnet).

```sh
curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh | bash -s -- --tailscale
```

`--tailscale` makes the endpoint reachable from your own devices only.
`--funnel` publishes it through [Tailscale Funnel](https://tailscale.com/kb/1223/funnel):

- Only this one service goes public. No router ports are opened, and your
  home IP stays hidden behind Tailscale's relays.
- Everything else on the server stays private, including other services and
  SSH.

Before the first run:

1. Enable **HTTPS certificates** for the tailnet in the admin console under
   [DNS](https://login.tailscale.com/admin/dns).
2. For `--funnel` only, allow Funnel in the
   [tailnet policy](https://login.tailscale.com/admin/acls). In the JSON
   editor, add this at the top level:
   ```json
   "nodeAttrs": [
     {"target": ["autogroup:member"], "attr": ["funnel"]},
   ],
   ```

Switch between private and public at any time:

```sh
sudo tailscale serve reset && sudo tailscale funnel --bg 7019   # public
sudo tailscale funnel reset && sudo tailscale serve --bg 7019   # private
```

### Tailscale in a Docker container

If Tailscale runs as a container (e.g. `tailscale/tailscale`) instead of on
the host, pass the command that reaches its CLI:

```sh
curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh \
  | TAILSCALE="docker exec tailscale tailscale" bash -s -- --funnel
```

- **Host networking** (`--net=host`): this is enough, because the container
  reaches QLever on port 7019 directly.
- **Bridge network:** also set `TS_TARGET` to QLever's address as the
  container sees it, usually the Docker bridge gateway, e.g.
  `TS_TARGET=http://172.17.0.1:7019`.
- **State:** the container needs a persistent state volume
  (`/var/lib/tailscale`). Otherwise the serve or Funnel setting is lost
  when the container restarts.

Prefix the switch commands above with `docker exec tailscale` in this case.

## Cloud VM with Caddy

On a VM with a public IP, run the script without a mode. Before that, open
ports 80 and 443 in the provider's firewall:

```sh
curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh | bash
```

- **Address:** Caddy gets a Let's Encrypt certificate for `<ip>.sslip.io`,
  a free DNS name that resolves to the server's IP.
- **Own domain:** point an A record at the server and pass the name:
  `... | bash -s -- sparql.example.org`.
- **Firewall:** the script also opens ports 80 and 443 in iptables, for
  images that block them by default.

## Check it

```sh
curl -s https://<site>/ -H 'Accept: application/sparql-results+json' \
  --data-urlencode 'query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }'
```

It should report about 4.5 million triples. For a query editor, open
[YASGUI](https://yasgui.triply.cc/) and enter the endpoint URL. QLever allows
cross-origin requests, so browser tools work.

## Operate it

```sh
sudo systemctl start managraph-update      # rebuild now
journalctl -u managraph-update -e          # last rebuild's log
systemctl list-timers managraph-update     # next scheduled run
cd ~/ManaGraph/qlever && uvx --python 3.12 qlever log   # QLever server log
```

**Rebuilds:** the timer runs on Mondays around 04:00; change `OnCalendar=`
in `/etc/systemd/system/managraph-update.timer` to move it. A rebuild takes
5 to 10 minutes.

- **Downtime:** the endpoint is down only for the last minute or two, while
  QLever reindexes.
- **Failures:** if the pipeline fails, for example on a SHACL violation, the
  rebuild stops before touching QLever and the previous index keeps serving.

**Load:** when idle, QLever holds a few GB of RAM and uses no CPU.

- **Per query:** each query is capped at 60 s and 2 GB of memory.
- **Results cache:** limited to 1 GB.
- **Public endpoints:** anyone can send queries, so many heavy ones at once
  will load the server.

**Access token:** privileged QLever commands, such as clearing the cache or
updates, need the token in `~/.managraph-token`. Public queries are
read-only.

## Files

| File | Purpose |
|---|---|
| [`setup.sh`](setup.sh) | One-time setup: packages, swap, repo, timer, first build, HTTPS |
| [`update.sh`](update.sh) | Pull, rebuild the graph, reindex and restart QLever |
| [`Caddyfile`](Caddyfile) | HTTPS reverse proxy for the cloud VM mode |
| [`managraph-update.service`](managraph-update.service), [`.timer`](managraph-update.timer) | The weekly rebuild |
