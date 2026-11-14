# Mirror-Leech Bot (HTTP/HTTPS build)

This fork is configured for direct HTTP/HTTPS downloads using Aria2, followed by upload through the bot's existing Telegram and Google Drive upload paths.

## Important changes

- BitTorrent and Metalink support are removed from the Aria2 build itself (`--disable-bittorrent --disable-metalink`).
- qBittorrent, SABnzbd, NZB, magnet, torrent search, torrent selection, and seeding components have been removed from the bot startup and source tree.
- The container is built from `python:3.13-slim-bookworm`; it does not inherit preinstalled download daemons from another Mirror-Leech image.
- `update.py` is not run on startup or restart, so this fork is not overwritten by upstream code.
- The old bot-wide `/bsetting` menu and web file-selection UI were removed with the qBittorrent/NZB settings and selector paths; configure the bot through `config.py` or environment variables.
- Aria2 starts locally on `127.0.0.1:6800`; its RPC endpoint is not exposed publicly.

## Build and run

1. Copy `config_sample.py` to `config.py` and fill in the required Telegram values.
2. Configure Google Drive credentials if you intend to use Google Drive uploads.
3. Build and run:

```sh
docker build -t mirror-leech-http .
docker run -d --name mirror-leech \\
  --restart unless-stopped \\
  --env-file .env \\
  mirror-leech-http
```

You can also supply the configuration through environment variables supported by `bot/core/config_manager.py`.

## Aria2 security and scope

This pass removes torrent/NZB components. Other non-torrent modules inherited from the upstream project (for example, some cloud and media download helpers) have not all been stripped yet; if you require the entire bot to accept only raw HTTP/HTTPS URLs, that is a separate cleanup pass.


Aria2's RPC listener is bound to loopback inside the container. The compiled binary excludes BitTorrent and Metalink support; setting an option in a config file cannot re-enable features that were not compiled into the binary.

Only use direct HTTP/HTTPS URLs for Aria2 downloads. This fork does not provide torrent, magnet, peer, tracker, or seeding workflows.
