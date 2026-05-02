package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

func chooseUploadChunkSize(configuredChunkSize int64, tokenMaxChunkBytes int64, preferredChunkSize int64) (int64, error) {
	chunkSize := tokenMaxChunkBytes
	if configuredChunkSize > 0 {
		chunkSize = configuredChunkSize
	}
	if preferredChunkSize > 0 {
		chunkSize = preferredChunkSize
	}

	if chunkSize <= 0 {
		return 0, fmt.Errorf("chunk size must be greater than zero")
	}
	if chunkSize > tokenMaxChunkBytes {
		return 0, fmt.Errorf("chunk size %d exceeds server max %d", chunkSize, tokenMaxChunkBytes)
	}

	return chunkSize, nil
}

func runUploadCommand(ctx context.Context, args []string) error {
	var cfg CommandConfig
	fs := flag.NewFlagSet("upload", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	bindCommonFlags(fs, &cfg, true)

	token := fs.String("token", "", "Upload token")
	rawURL := fs.String("url", "", "FBC upload or token URL")
	filePath := fs.String("file", "", "Path to the local file to upload")
	uploadID := fs.String("upload-id", "", "Existing upload ID to resume instead of initiating a new upload")
	metadataFile := fs.String("metadata-file", "", "Path to a JSON object to send as meta_data")
	metadataJSON := fs.String("metadata-json", "", "Inline JSON object to send as meta_data")
	var metadataEntries metadataFlag
	fs.Var(&metadataEntries, "metadata", "Metadata entry as key=value; repeat for nested paths like series.title=Example")
	declaredFileType := fs.String("filetype", "", "Optional MIME type to declare during initiation")
	chunkSizeRaw := fs.String("chunk-size", defaultUploadChunkRaw, "Override PATCH chunk size; defaults to the server recommendation")
	setUsage(fs, "fbc upload --token <upload-token> --file ./path [options]", "Uses server-side HEAD responses as the source of truth for resume.", "Metadata sources can be combined. --metadata entries override keys from --metadata-file or --metadata-json.")

	if err := fs.Parse(args); err != nil {
		return err
	}
	if err := requireNoArgs(fs); err != nil {
		return err
	}
	if strings.TrimSpace(*rawURL) != "" {
		target, err := parseResourceTarget(cfg.BaseURL, *rawURL)
		if err != nil {
			return err
		}

		if target.Token == "" {
			return fmt.Errorf("upload URL %q did not contain a token", *rawURL)
		}

		cfg.BaseURL = target.BaseURL
		if strings.TrimSpace(*token) == "" {
			*token = target.Token
		}
	}
	if strings.TrimSpace(*token) == "" {
		return fmt.Errorf("--token or --url is required")
	}
	if strings.TrimSpace(*filePath) == "" {
		return fmt.Errorf("--file is required")
	}

	info, err := os.Stat(*filePath)
	if err != nil {
		return fmt.Errorf("stat %q: %w", *filePath, err)
	}
	if info.IsDir() {
		return fmt.Errorf("%q is a directory", *filePath)
	}
	if info.Size() <= 0 {
		return fmt.Errorf("file size must be greater than zero")
	}

	chunkSizeOverride := strings.TrimSpace(*chunkSizeRaw) != ""
	configuredChunkSize := int64(0)
	if chunkSizeOverride {
		configuredChunkSize, err = parseByteSize(*chunkSizeRaw)
		if err != nil {
			return fmt.Errorf("parse --chunk-size: %w", err)
		}
	}

	client, err := NewClient(cfg.BaseURL, cfg.APIKey)
	if err != nil {
		return err
	}

	tokenInfo, err := client.GetTokenInfo(ctx, *token)
	if err != nil {
		return err
	}
	if tokenInfo.Token == nil {
		return fmt.Errorf("token %q is not an upload token", *token)
	}

	resolvedUploadID := strings.TrimSpace(*uploadID)
	selectedChunkSize := configuredChunkSize
	recommendedChunkSize := int64(0)
	if resolvedUploadID == "" {
		metadata, err := loadCombinedMetadata(*metadataFile, *metadataJSON, []string(metadataEntries))
		if err != nil {
			return err
		}

		initResponse, err := client.InitiateUpload(ctx, *token, UploadRequest{
			MetaData:  metadata,
			Filename:  filepath.Base(*filePath),
			Filetype:  detectDeclaredMIME(*filePath, *declaredFileType),
			SizeBytes: info.Size(),
		})
		if err != nil {
			return err
		}

		resolvedUploadID = initResponse.UploadID
		recommendedChunkSize = initResponse.RecommendedChunkBytes
		fmt.Fprintf(os.Stderr, "Started upload %s\n", resolvedUploadID)
	} else if strings.TrimSpace(*metadataFile) != "" || strings.TrimSpace(*metadataJSON) != "" || len(metadataEntries) > 0 {
		fmt.Fprintln(os.Stderr, "Ignoring metadata flags because --upload-id resumes an existing upload")
		for _, upload := range tokenInfo.Uploads {
			if upload.PublicID == resolvedUploadID {
				if upload.RecommendedChunkBytes != nil {
					recommendedChunkSize = *upload.RecommendedChunkBytes
				}
				break
			}
		}
	}

	if !chunkSizeOverride {
		selectedChunkSize, err = chooseUploadChunkSize(0, tokenInfo.MaxChunkBytes, recommendedChunkSize)
		if err != nil {
			return err
		}
	} else {
		selectedChunkSize, err = chooseUploadChunkSize(configuredChunkSize, tokenInfo.MaxChunkBytes, 0)
		if err != nil {
			return err
		}
	}

	chunkSize, err := intFromInt64(selectedChunkSize, "chunk size")
	if err != nil {
		return err
	}

	headInfo, err := client.HeadUpload(ctx, resolvedUploadID)
	if err != nil {
		return err
	}
	if headInfo.Length != info.Size() {
		return fmt.Errorf("server upload length is %d bytes but local file is %d bytes", headInfo.Length, info.Size())
	}

	fileHandle, err := os.Open(*filePath)
	if err != nil {
		return fmt.Errorf("open %q: %w", *filePath, err)
	}
	defer fileHandle.Close()

	offset := headInfo.Offset
	if offset > info.Size() {
		return fmt.Errorf("server offset %d exceeds local file size %d", offset, info.Size())
	}
	if offset > 0 {
		fmt.Fprintf(os.Stderr, "Resuming upload %s from byte %d\n", resolvedUploadID, offset)
	}

	buffer := make([]byte, chunkSize)
	for offset < info.Size() {
		remaining := info.Size() - offset
		chunk := buffer
		if remaining < int64(len(chunk)) {
			chunk = chunk[:remaining]
		}

		readBytes, err := fileHandle.ReadAt(chunk, offset)
		if err != nil && !errors.Is(err, io.EOF) {
			return fmt.Errorf("read file at offset %d: %w", offset, err)
		}
		if readBytes == 0 {
			return fmt.Errorf("read zero bytes at offset %d before upload finished", offset)
		}

		nextOffset, err := uploadChunkWithResume(ctx, client, resolvedUploadID, offset, chunk[:readBytes])
		if err != nil {
			return err
		}
		offset = nextOffset
	}

	record, err := client.CompleteUpload(ctx, resolvedUploadID, *token)
	if err != nil {
		return err
	}

	result := UploadCommandResult{
		UploadID:              resolvedUploadID,
		DownloadToken:         tokenInfo.DownloadToken,
		InfoURL:               client.ResolveString(fileInfoPath(tokenInfo.DownloadToken, resolvedUploadID)),
		DownloadURL:           client.ResolveString(fileDownloadPath(tokenInfo.DownloadToken, resolvedUploadID)),
		ResumedFrom:           headInfo.Offset,
		ChunkSizeBytes:        selectedChunkSize,
		RecommendedChunkBytes: recommendedChunkSize,
		Record:                record,
	}

	if cfg.JSON {
		return printJSON(os.Stdout, result)
	}

	fmt.Fprintf(os.Stdout, "Upload ID: %s\n", result.UploadID)
	fmt.Fprintf(os.Stdout, "Status: %s\n", result.Record.Status)
	fmt.Fprintf(os.Stdout, "Resumed from: %d\n", result.ResumedFrom)
	fmt.Fprintf(os.Stdout, "Chunk size: %d bytes (%s)\n", result.ChunkSizeBytes, formatBytes(result.ChunkSizeBytes))
	fmt.Fprintf(os.Stdout, "Info URL: %s\n", result.InfoURL)
	fmt.Fprintf(os.Stdout, "Download URL: %s\n", result.DownloadURL)
	if result.Record.Status == "postprocessing" {
		fmt.Fprintln(os.Stdout, "The upload is accepted and queued for post-processing.")
	}

	return nil
}

func uploadChunkWithResume(ctx context.Context, client *Client, uploadID string, offset int64, chunk []byte) (int64, error) {
	const maxAttempts = 3
	checksum := buildChecksumHeader(chunk)
	var lastErr error

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		headInfo, err := client.PatchUpload(ctx, uploadID, offset, chunk, checksum)
		if err == nil {
			if headInfo.Offset < offset {
				return 0, fmt.Errorf("server offset moved backwards from %d to %d", offset, headInfo.Offset)
			}
			return headInfo.Offset, nil
		}

		lastErr = err
		var httpErr *HTTPError
		if errors.As(err, &httpErr) {
			if httpErr.StatusCode != http.StatusConflict && httpErr.StatusCode != checksumStatusCode {
				return 0, err
			}
		}

		if ctx.Err() != nil {
			return 0, ctx.Err()
		}

		headInfo, headErr := client.HeadUpload(ctx, uploadID)
		if headErr != nil {
			return 0, fmt.Errorf("upload chunk failed: %w; resume probe also failed: %v", err, headErr)
		}

		switch {
		case headInfo.Offset > offset:
			return headInfo.Offset, nil
		case headInfo.Offset == offset:
			continue
		default:
			return 0, fmt.Errorf("server offset moved backwards from %d to %d", offset, headInfo.Offset)
		}
	}

	return 0, fmt.Errorf("failed to upload chunk at offset %d after %d attempts: %w", offset, maxAttempts, lastErr)
}

func buildChecksumHeader(chunk []byte) string {
	digest := sha256.Sum256(chunk)
	return "sha256 " + base64.StdEncoding.EncodeToString(digest[:])
}
