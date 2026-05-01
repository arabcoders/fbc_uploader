package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strings"
)

func runInfoCommand(ctx context.Context, args []string) error {
	var cfg CommandConfig
	fs := flag.NewFlagSet("info", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	bindCommonFlags(fs, &cfg, false)

	token := fs.String("token", "", "Upload token or download token to inspect")
	downloadToken := fs.String("download-token", "", "Download token for a specific uploaded file")
	uploadID := fs.String("upload-id", "", "Upload ID for a specific uploaded file")
	rawURL := fs.String("url", "", "FBC token, share, info, or download URL")
	setUsage(fs, "fbc info [options]", "Examples:", "  fbc info --token <token>", "  fbc info --download-token <token> --upload-id <id>", "  fbc info --url https://example.com/api/tokens/fbc_x/uploads/abc")

	if err := fs.Parse(args); err != nil {
		return err
	}
	if err := requireNoArgs(fs); err != nil {
		return err
	}

	client, err := NewClient(cfg.BaseURL, cfg.APIKey)
	if err != nil {
		return err
	}

	var output any
	switch {
	case strings.TrimSpace(*rawURL) != "":
		target, err := parseResourceTarget(cfg.BaseURL, *rawURL)
		if err != nil {
			return err
		}

		client, err = NewClient(target.BaseURL, cfg.APIKey)
		if err != nil {
			return err
		}

		if target.UploadID != "" {
			output, err = client.GetFileInfo(ctx, target.Token, target.UploadID)
			if err != nil {
				return err
			}
		} else {
			output, err = client.GetTokenInfo(ctx, target.Token)
			if err != nil {
				return err
			}
		}
	case strings.TrimSpace(*token) != "":
		output, err = client.GetTokenInfo(ctx, *token)
		if err != nil {
			return err
		}
	case strings.TrimSpace(*downloadToken) != "":
		if strings.TrimSpace(*uploadID) == "" {
			output, err = client.GetTokenInfo(ctx, *downloadToken)
		} else {
			output, err = client.GetFileInfo(ctx, *downloadToken, *uploadID)
		}
		if err != nil {
			return err
		}
	default:
		return fmt.Errorf("provide --token, --url, or --download-token with optional --upload-id")
	}

	return printJSON(os.Stdout, output)
}
