package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"
)

func runCreateCommand(ctx context.Context, args []string) error {
	var cfg CommandConfig
	fs := flag.NewFlagSet("create", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	bindCommonFlags(fs, &cfg, true)

	maxUploads := fs.Int("max-uploads", 1, "Maximum number of uploads allowed for the token")
	maxSize := fs.String("max-size", "1G", "Maximum size per upload, for example 500M or 2G")
	expiresAt := fs.String("expires-at", "", "Optional token expiry in RFC3339 or YYYY-MM-DD format")
	var allowedMime stringListFlag
	fs.Var(&allowedMime, "allowed-mime", "Allowed MIME pattern (repeat or comma-separated)")
	setUsage(fs, "fbc create [options]", "Creates a new upload token and matching download token.")

	if err := fs.Parse(args); err != nil {
		return err
	}
	if err := requireNoArgs(fs); err != nil {
		return err
	}
	if err := requireAPIKey(cfg.APIKey); err != nil {
		return err
	}

	maxSizeBytes, err := parseByteSize(*maxSize)
	if err != nil {
		return fmt.Errorf("parse --max-size: %w", err)
	}

	var expiry *time.Time
	if strings.TrimSpace(*expiresAt) != "" {
		parsed, err := parseExpiry(*expiresAt)
		if err != nil {
			return fmt.Errorf("parse --expires-at: %w", err)
		}
		expiry = &parsed
	}

	client, err := NewClient(cfg.BaseURL, cfg.APIKey)
	if err != nil {
		return err
	}

	payload := CreateTokenRequest{
		MaxUploads:   *maxUploads,
		MaxSizeBytes: maxSizeBytes,
		AllowedMime:  []string(allowedMime),
	}
	if expiry != nil {
		payload.ExpiryDatetime = expiry
	}

	response, err := client.CreateToken(ctx, payload)
	if err != nil {
		return err
	}

	result := CreateCommandResult{
		Token:         response.Token,
		DownloadToken: response.DownloadToken,
		UploadPageURL: client.ResolveString(response.UploadURL),
		ShareURL:      client.ResolveString(sharePath(response.DownloadToken)),
		ExpiresAt:     response.ExpiresAt,
		MaxUploads:    response.MaxUploads,
		MaxSizeBytes:  response.MaxSizeBytes,
		AllowedMime:   response.AllowedMime,
	}

	if cfg.JSON {
		return printJSON(os.Stdout, result)
	}

	fmt.Fprintf(os.Stdout, "Upload token: %s\n", result.Token)
	fmt.Fprintf(os.Stdout, "Download token: %s\n", result.DownloadToken)
	fmt.Fprintf(os.Stdout, "Upload page: %s\n", result.UploadPageURL)
	fmt.Fprintf(os.Stdout, "Share page: %s\n", result.ShareURL)
	fmt.Fprintf(os.Stdout, "Expires at: %s\n", result.ExpiresAt.Format(time.RFC3339))
	fmt.Fprintf(os.Stdout, "Max uploads: %d\n", result.MaxUploads)
	fmt.Fprintf(os.Stdout, "Max size: %d bytes (%s)\n", result.MaxSizeBytes, formatBytes(result.MaxSizeBytes))
	if len(result.AllowedMime) > 0 {
		fmt.Fprintf(os.Stdout, "Allowed MIME: %s\n", strings.Join(result.AllowedMime, ", "))
	}

	return nil
}
