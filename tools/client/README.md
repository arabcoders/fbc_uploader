# FBC CLI

`tools/client` contains a small Go CLI for FBC Uploader that uses only the Go standard library.

The client targets Go 1.20+.

Tagged GitHub releases publish prebuilt binaries for Linux, macOS, and Windows on both `amd64` and `arm64`.

## Commands

- `create`: create an upload token and matching download token
- `info`: inspect a token or a specific uploaded file
- `upload`: upload a local file with server-driven resume via TUS `HEAD`/`PATCH`
- `download`: download a completed file by token/upload ID or URL
- `cancel`: cancel an incomplete upload

## Environment

The CLI reads the same environment variables already used elsewhere in this repo:

- `FBC_PUBLIC_BASE_URL`
- `FBC_ADMIN_API_KEY`

Flags override environment variables when both are provided.

## Build

```bash
cd tools/client
go build -o fbc .
```

Build Linux binaries for both `amd64` and `arm64`:

```bash
cd tools/client
./build.sh
```

Outputs:

- `tools/client/dist/fbc-linux-amd64`
- `tools/client/dist/fbc-linux-arm64`

## Examples

Create a token pair:

```bash
export FBC_PUBLIC_BASE_URL=https://example.com
export FBC_ADMIN_API_KEY=YOUR_ADMIN_KEY

./fbc create --max-uploads 3 --max-size 2G --allowed-mime video/*
```

Inspect a token:

```bash
./fbc info --token YOUR_UPLOAD_TOKEN
./fbc info --url https://example.com/f/fbc_download_token
```

Upload a file with nested metadata:

```bash
./fbc upload \
  --token YOUR_UPLOAD_TOKEN \
  --file ./episode.mp4 \
  --metadata series.title="Example Show" \
  --metadata episode=2
```

Or provide the same metadata as JSON:

```bash
./fbc upload \
  --token YOUR_UPLOAD_TOKEN \
  --file ./episode.mp4 \
  --metadata-json '{"series":{"title":"Example Show"},"episode":2}'
```

Resume an upload using the existing upload ID:

```bash
./fbc upload \
  --token YOUR_UPLOAD_TOKEN \
  --upload-id EXISTING_UPLOAD_ID \
  --file ./episode.mp4
```

Download a file:

```bash
./fbc download --download-token fbc_download_token --upload-id EXISTING_UPLOAD_ID
./fbc download --url https://example.com/api/tokens/fbc_download_token/uploads/EXISTING_UPLOAD_ID/download
```

Cancel an incomplete upload:

```bash
./fbc cancel --token YOUR_UPLOAD_TOKEN --upload-id EXISTING_UPLOAD_ID
```

## Notes

- Resume is server-driven. The CLI uses `HEAD /api/uploads/{upload_id}/tus` as the source of truth.
- By default, upload chunk size follows the server-provided `recommended_chunk_bytes` value. Use `--chunk-size` to override it explicitly.
- Uploads are only finalized after `POST /api/uploads/{upload_id}/complete?token=...`.
- Restricted downloads work by sending `Authorization: Bearer <FBC_ADMIN_API_KEY>` when present.
- Metadata must be a JSON object and may be nested.
- For fresh uploads, the CLI first asks `/api/metadata/extract` to prefill metadata from the filename.
- `--metadata key=value` may be repeated, supports dot paths like `series.title=Example`, and overrides matching keys from `--metadata-file` or `--metadata-json`.
