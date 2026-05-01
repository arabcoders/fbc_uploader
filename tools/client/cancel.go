package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strings"
)

func runCancelCommand(ctx context.Context, args []string) error {
	var cfg CommandConfig
	fs := flag.NewFlagSet("cancel", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	bindCommonFlags(fs, &cfg, true)

	token := fs.String("token", "", "Upload token")
	uploadID := fs.String("upload-id", "", "Upload ID to cancel")
	setUsage(fs, "fbc cancel --token <upload-token> --upload-id <id>")

	if err := fs.Parse(args); err != nil {
		return err
	}
	if err := requireNoArgs(fs); err != nil {
		return err
	}
	if strings.TrimSpace(*token) == "" {
		return fmt.Errorf("--token is required")
	}
	if strings.TrimSpace(*uploadID) == "" {
		return fmt.Errorf("--upload-id is required")
	}

	client, err := NewClient(cfg.BaseURL, cfg.APIKey)
	if err != nil {
		return err
	}

	response, err := client.CancelUpload(ctx, *uploadID, *token)
	if err != nil {
		return err
	}

	result := CancelCommandResult{
		UploadID:         *uploadID,
		Message:          response.Message,
		RemainingUploads: response.RemainingUploads,
	}

	if cfg.JSON {
		return printJSON(os.Stdout, result)
	}

	fmt.Fprintf(os.Stdout, "%s\n", result.Message)
	fmt.Fprintf(os.Stdout, "Upload ID: %s\n", result.UploadID)
	fmt.Fprintf(os.Stdout, "Remaining uploads: %d\n", result.RemainingUploads)

	return nil
}
