# Deploying the endpoint

Runs the ManaGraph SPARQL endpoint on one Ubuntu server: the pipeline builds
the graph on the server, QLever serves it, Tailscale or Caddy adds HTTPS, and
a systemd timer rebuilds everything weekly from fresh Scryfall data.

```
Scryfall bulk data ──► uv run managraph ──► qlever index ──► QLever :7019 ──► Tailscale / Caddy :443 ──► https://<site>/
                       (weekly, managraph-update.timer)
```

| File | Purpose |
|---|---|
| [`setup.sh`](setup.sh) | One-time setup: Docker, uv, swap, timer, first build, HTTPS |
| [`update.sh`](update.sh) | Pull, rebuild the graph, reindex, restart QLever |
| [`Caddyfile`](Caddyfile) | HTTPS reverse proxy to QLever |
| [`managraph-update.service`](managraph-update.service), [`.timer`](managraph-update.timer) | Weekly rebuild, Mondays around 04:00 |

## Home server with Tailscale

Any Ubuntu machine with 12 GB RAM or more that is on your
[tailnet](https://tailscale.com/kb/1136/tailnet). No router ports are opened.

```sh
curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh | bash -s -- --tailscale
```

The endpoint is `https://<machine>.<tailnet>.ts.net/`, reachable only from your
own devices. The first run asks you to enable HTTPS certificates for the
tailnet if they are off; follow the link it prints.

To make it public, use `--funnel` instead, or switch later:

```sh
sudo tailscale serve reset && sudo tailscale funnel --bg 7019   # public
sudo tailscale funnel reset && sudo tailscale serve --bg 7019   # back to private
```

Funnel needs the `funnel` attribute in the tailnet policy; the command prints a
link to enable it. Traffic goes through Tailscale's relays, so your home IP
stays hidden. Anyone can then send queries: each is capped by the 60 s
timeout, but many heavy ones at once will load the server.

## Oracle Cloud Always Free

The Always Free tier includes an Arm VM with up to 4 cores and 24 GB RAM at no
cost, enough for the pipeline (~9 GB peak) and QLever (`adfreiburg/qlever` has
an arm64 image).

1. Sign up at <https://cloud.oracle.com>. A card is needed for verification;
   Always Free resources are not charged.
2. **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 24.04**
   - Shape: **Ampere → VM.Standard.A1.Flex**, 4 OCPUs and 24 GB memory, or
     2 OCPUs and 12 GB, which gets capacity more often and is enough (the
     setup adds 8 GB swap for the rebuild peak). Resize later with
     **Stop → Edit → Shape**.
   - Boot volume: 100 GB (Always Free covers 200 GB in total)
   - Add your SSH public key.
   - If creation fails with "Out of capacity", try another availability
     domain or retry later; A1 capacity is often short in popular regions.
3. **Open ports 80 and 443**: on the instance page, open the subnet →
   **Security Lists → Default Security List → Add Ingress Rules**: source
   `0.0.0.0/0`, TCP, destination ports `80,443`.
4. SSH in and run the setup:
   ```sh
   ssh ubuntu@<public-ip>
   curl -fsSL https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/main/deploy/setup.sh | bash
   ```
   It prints the endpoint URL at the end, e.g. `https://203-0-113-7.sslip.io/`.
   To use your own domain instead, point an A record at the server and pass
   the name: `... | bash -s -- sparql.example.org`.

Oracle reclaims Always Free instances it considers idle (over 7 days, CPU,
network and memory all mostly under 20%), and a quiet endpoint can fall under
that. The usual fix is to upgrade the account to **Pay As You Go**: Always Free
resources stay free and are no longer reclaimed. Set a budget alert at a few
dollars to catch anything billable. If an instance is reclaimed anyway, rerun
steps 2 to 4.

## Check it

```sh
curl -s https://<site>/ -H 'Accept: application/sparql-results+json' \
  --data-urlencode 'query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }'
```

## Operate it

```sh
sudo systemctl start managraph-update      # rebuild now
journalctl -u managraph-update -e          # last rebuild's log
systemctl list-timers managraph-update     # next scheduled run
cd ~/ManaGraph/qlever && uvx --python 3.12 qlever log   # QLever server log
```

A rebuild stops the endpoint for the minute or two the index takes. If the
pipeline fails (for example on a SHACL violation), the rebuild stops before
touching QLever and the previous index keeps serving.

The access token for privileged QLever commands (such as clearing the cache)
is in `~/.managraph-token` on the server.
