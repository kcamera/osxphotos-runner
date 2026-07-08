# Dashboard deployment (NAS)

One-time setup, run **on the NAS as kcamera** (Claude prepares files but
does not write to the NAS):

```sh
# 1. Copy the site + compose files into place (run from any machine that
#    has the repo; here shown from the MacBook/Mini repo root):
rsync -rt dashboard/site dashboard/docker-compose.yml dashboard/Caddyfile \
    kcamera@nas:Websites/osxphotos-dashboard/

# 2. On the NAS, start it:
cd ~/Websites/osxphotos-dashboard && docker compose up -d
```

Then browse to `http://nas:8088` (change the port in docker-compose.yml
if 8088 is taken). On the phone: open it in Safari → Share → Add to Home
Screen.

Layout on the NAS after setup:

```
~/Websites/osxphotos-dashboard/
├── docker-compose.yml
├── Caddyfile
├── site/          # static dashboard (this repo's dashboard/site/)
└── data/          # rsync publish target of the Mini — never touched here
```

Updating the site later: re-run the same rsync, no container restart
needed (Caddy serves the files live).

Notes:
- Plain HTTP on the LAN: no TLS means no service worker, deliberately.
  Add-to-Home-Screen still works via the manifest + iOS meta tags.
- `data/*` is served with `Cache-Control: no-store`; the page also
  cache-busts and refetches on focus and every 5 minutes.
- "Exported" counts files (original + AAE + XMP ≈ 1.5–2.5× photos),
  not photos.
