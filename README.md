# FBC Uploader

FBC Uploader is a file upload service that allows users to upload files without creating accounts. Administrators generate upload tokens with defined limits and restrictions to control access and usage. Public downloads can be enabled if required, but the primary purpose of the service is to accept uploads from unauthenticated clients and expose the uploaded content to automation and downstream systems through an administrative API.

The service supports resumable uploads using the TUS protocol, token-based authentication, and dynamic metadata validation driven by a configurable schema.

# Installation

## Run using docker command

```bash
mkdir -p ./{config,downloads} && docker run -d --rm --user "${UID}:${UID}" --name fbc_uploader \
-p 8000:8000 -v ./config:/config:rw -v ./downloads:/downloads:rw \
ghcr.io/arabcoders/fbc_uploader:latest
```

Then you can access the WebUI at `http://localhost:8000`.

> [!NOTE]
> If you are using `podman` instead of `docker`, you can use the same command, but you need to change the user to `0:0`
> it will appears to be running as root, but it will run as the user who started the container.

## Using compose file

The following is an example of a `compose.yaml` file that can be used to run FBC Uploader.

```yaml
services:
  fbc_uploader:
    user: "${UID:-1000}:${UID:-1000}" # change this to your user id and group id, for example: "1000:1000"
    image: ghcr.io/arabcoders/fbc_uploader:latest
    container_name: fbc_uploader
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./config:/config:rw
      - ./downloads:/downloads:rw
```

> [!IMPORTANT]
> Make sure to change the `user` line to match your user id and group id

```bash
mkdir -p ./{config,downloads} && docker compose -f compose.yaml up -d
```

Then you can access the WebUI at `http://localhost:8000`.

> [!NOTE]
> you can use podman-compose instead of docker-compose, as it supports the same syntax. However, you should change the 
> user to `0:0` it will appears to be running as root, but it will run as the user who started the container.

## Environment Variables

All configuration is done via environment variables prefixed with `FBC_`:

| Variable                            | Default          | Description                                                                       |
| ----------------------------------- | ---------------- | --------------------------------------------------------------------------------- |
| `FBC_CONFIG_PATH`                   | `./data/config`  | Configuration directory                                                           |
| `FBC_STORAGE_PATH`                  | `./data/uploads` | Directory for uploaded files                                                      |
| `FBC_ADMIN_API_KEY`                 | Auto-generated   | Admin API key (stored in `{config_path}/secret.key` if not set)                   |
| `FBC_DEFAULT_TOKEN_TTL_HOURS`       | `24`             | Default token expiration in hours (1-720)                                         |
| `FBC_CLEANUP_INTERVAL_SECONDS`      | `3600`           | Interval between cleanup job runs                                                 |
| `FBC_INCOMPLETE_TTL_HOURS`          | `24`             | Time-to-live for incomplete uploads (0 to disable)                                |
| `FBC_DISABLED_TOKENS_TTL_DAYS`      | `30`             | Days to keep disabled tokens before deletion (0 to disable)                       |
| `FBC_DELETE_FILES_ON_TOKEN_CLEANUP` | `true`           | Delete associated files when cleaning up disabled tokens                          |
| `FBC_MAX_CHUNK_BYTES`               | `94371840`       | Maximum TUS chunk size. Default to (90MB)                                         |
| `FBC_MAX_REMUX_BYTES`               | `5368709120`     | Maximum file size eligible for copy-remux to MP4 during post-processing (5GB)     |
| `FBC_POSTPROCESSING_WORKERS`        | `4`              | Number of uploads processed concurrently in the background post-processing queue  |
| `FBC_EMBED_PREVIEW_CLIP_SECONDS`    | `10`             | Length of generated bot preview clips in seconds (0 disables preview generation)   |
| `FBC_EMBED_PREVIEW_MIN_SIZE_BYTES`  | `204472320`      | Only generate bot preview clips for videos at or above this size in bytes (195 MB); `0` disables the feature |
| `FBC_ALLOW_PUBLIC_DOWNLOADS`        | `false`          | Allow public downloads without authentication                                     |
| `FBC_TRUST_PROXY_HEADERS`           | `false`          | Trust `X-Forwarded-*` headers, but only from proxies in `FBC_FORWARDED_ALLOW_IPS` |
| `FBC_FORWARDED_ALLOW_IPS`           | `127.0.0.1,::1`  | Comma-separated trusted proxy IPs or CIDRs allowed to supply forwarded headers    |

When running behind a reverse proxy, `FBC_TRUST_PROXY_HEADERS=true` is not enough on its own. You must also set `FBC_FORWARDED_ALLOW_IPS` to the proxy IPs or networks that connect directly to FBC Uploader, such as a Docker bridge subnet like `172.23.0.0/16`.

If you leave `FBC_FORWARDED_ALLOW_IPS` at its default, only local loopback proxies are trusted. This protects against clients forging `X-Forwarded-For`, `X-Forwarded-Proto`, or `X-Forwarded-Host` when the app is exposed directly.

Uploaded multimedia files are post-processed after upload completion. Browser-safe `mp4` and `webm` files are kept as-is. Compatible non-MP4 video containers may be copy-remuxed into `mp4` for better playback compatibility without transcoding. Files larger than `FBC_MAX_REMUX_BYTES` skip remux and still complete normally. Large videos can also get short MP4 bot-preview sidecars for embeds, controlled by `FBC_EMBED_PREVIEW_CLIP_SECONDS` and `FBC_EMBED_PREVIEW_MIN_SIZE_BYTES`. Setting `FBC_EMBED_PREVIEW_MIN_SIZE_BYTES=0` disables bot preview sidecars entirely. The background worker pool processes up to `FBC_POSTPROCESSING_WORKERS` uploads concurrently.

## Dynamic Metadata Schema

Upload metadata is configurable via `{config_path}/metadata.json`. Define custom fields with validation rules, types, and UI hints.
The schema is validated on both client and server. See [metadata.md](metadata.md) for full documentation.

## yt-dlp Extractor

A yt-dlp extractor is available in `tools/fbc_extractor.py` for downloading files directly from FBC Uploader instances using yt-dlp.

**Usage:**

```bash
# Add extractor to yt-dlp plugins directory
mkdir -p ~/.config/yt-dlp/plugins/my_plugins/yt_dlp_plugins/extractor
cp tools/fbc_extractor.py ~/.config/yt-dlp/plugins/my_plugins/yt_dlp_plugins/extractor/

# Download using download token URL
yt-dlp --username key --password YOUR_API_KEY "https://yourdomain.com/api/tokens/fbc_token_here/uploads"

# Or set FBC_API_KEY environment variable
export FBC_API_KEY=YOUR_API_KEY
yt-dlp "https://yourdomain.com/api/tokens/fbc_token_here/uploads"
```

The extractor authenticates using the admin API key and downloads all completed uploads associated with the token.

## Go CLI

A standalone Go client lives in `tools/client`.

It is a pure CLI and uses only the Go standard library. It supports token creation, upload with server-driven resume, download, file/token inspection, and upload cancellation.

Tagged releases publish prebuilt Go client binaries for Linux, macOS, and Windows on `amd64` and `arm64`.

**Environment variables:**

```bash
export FBC_PUBLIC_BASE_URL=https://yourdomain.com
export FBC_ADMIN_API_KEY=YOUR_API_KEY
```

**Build:**

```bash
cd tools/client
go build -o fbc .
```

Build Linux binaries for both `amd64` and `arm64`:

```bash
cd tools/client
./build.sh
```

**Examples:**

```bash
# Create a token pair
./fbc create --max-uploads 3 --max-size 2G --allowed-mime video/*

# Inspect a token
./fbc info --token YOUR_UPLOAD_TOKEN

# Upload a file with nested metadata
./fbc upload \
  --token YOUR_UPLOAD_TOKEN \
  --file ./episode.mp4 \
  --metadata series.title="Example Show" \
  --metadata episode=2

# Or send the same metadata as JSON
./fbc upload \
  --token YOUR_UPLOAD_TOKEN \
  --file ./episode.mp4 \
  --metadata-json '{"series":{"title":"Example Show"},"episode":2}'

# Resume an upload using the existing upload ID
./fbc upload \
  --token YOUR_UPLOAD_TOKEN \
  --upload-id EXISTING_UPLOAD_ID \
  --file ./episode.mp4

# Download a completed file
./fbc download --download-token fbc_download_token --upload-id EXISTING_UPLOAD_ID
```

See `tools/client/README.md` for more details.

## API Documentation

See [API.md](API.md) for complete API documentation.

## Contributing (Bug reports only)

Bug reports are welcome. Please open an issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version, etc.)

> [!NOTE]
> I am unlikely to accept feature requests. This project serves a specific use case and is maintained primarily for my own needs.
