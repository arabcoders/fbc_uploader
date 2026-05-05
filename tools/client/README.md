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

- Re-running `upload` with the same `--upload-id` resumes from the server's current offset; you do not need to track local state yourself.
- For new uploads, the CLI asks the server to extract metadata from the filename first, then applies values from `--metadata-file`, `--metadata-json`, and repeated `--metadata key=value` flags.
- `--metadata key=value` supports dotted paths like `series.title=Example`, and explicit flag values win over matching keys from JSON sources.
- The CLI completes uploads automatically after the final chunk is accepted.
- `info --url` and `download --url` accept normal share links as well as direct API URLs.
