package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func runDownloadCommand(ctx context.Context, args []string) error {
	var cfg CommandConfig
	fs := flag.NewFlagSet("download", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	bindCommonFlags(fs, &cfg, true)

	rawURL := fs.String("url", "", "FBC share, token, info, or download URL")
	downloadToken := fs.String("download-token", "", "Download token")
	uploadID := fs.String("upload-id", "", "Upload ID")
	output := fs.String("output", "", "Output path, directory, or - for stdout")
	setUsage(fs, "fbc download [--url <url> | --download-token <token> --upload-id <id>] [options]")

	if err := fs.Parse(args); err != nil {
		return err
	}
	if err := requireNoArgs(fs); err != nil {
		return err
	}
	if strings.TrimSpace(*output) == "-" && cfg.JSON {
		return fmt.Errorf("--json cannot be used when --output - writes file data to stdout")
	}

	client, err := NewClient(cfg.BaseURL, cfg.APIKey)
	if err != nil {
		return err
	}

	resolvedToken := strings.TrimSpace(*downloadToken)
	resolvedUploadID := strings.TrimSpace(*uploadID)
	if strings.TrimSpace(*rawURL) != "" {
		target, err := parseResourceTarget(cfg.BaseURL, *rawURL)
		if err != nil {
			return err
		}

		client, err = NewClient(target.BaseURL, cfg.APIKey)
		if err != nil {
			return err
		}

		resolvedToken = target.Token
		resolvedUploadID = target.UploadID
	}

	if resolvedToken == "" {
		return fmt.Errorf("provide --url or --download-token")
	}

	if resolvedUploadID == "" {
		tokenInfo, err := client.GetTokenInfo(ctx, resolvedToken)
		if err != nil {
			return err
		}

		upload, err := selectCompletedUpload(tokenInfo)
		if err != nil {
			return err
		}
		resolvedToken = tokenInfo.DownloadToken
		resolvedUploadID = upload.PublicID
	}

	record, err := client.GetFileInfo(ctx, resolvedToken, resolvedUploadID)
	if err != nil {
		return err
	}

	fallbackName := resolvedUploadID
	if record.Ext != nil && strings.TrimSpace(*record.Ext) != "" {
		fallbackName = fallbackName + "." + *record.Ext
	}

	filename := fallbackName
	if record.Filename != nil {
		filename = sanitizeFilename(*record.Filename, fallbackName)
	}

	var writer *os.File
	var outputPath string
	if strings.TrimSpace(*output) == "-" {
		writer = os.Stdout
		outputPath = ""
	} else {
		outputPath, err = resolveOutputPath(*output, filename)
		if err != nil {
			return err
		}

		writer, err = os.Create(outputPath)
		if err != nil {
			return fmt.Errorf("create %q: %w", outputPath, err)
		}
		defer writer.Close()
	}

	bytesWritten, err := client.DownloadFile(ctx, resolvedToken, resolvedUploadID, writer)
	if err != nil {
		return err
	}

	result := DownloadCommandResult{
		UploadID:      resolvedUploadID,
		DownloadToken: resolvedToken,
		OutputPath:    outputPath,
		Filename:      filename,
		BytesWritten:  bytesWritten,
	}

	if strings.TrimSpace(*output) == "-" {
		fmt.Fprintf(os.Stderr, "Downloaded %s (%d bytes)\n", filename, bytesWritten)
		return nil
	}

	if cfg.JSON {
		return printJSON(os.Stdout, result)
	}

	fmt.Fprintf(os.Stdout, "Downloaded: %s\n", result.Filename)
	fmt.Fprintf(os.Stdout, "Upload ID: %s\n", result.UploadID)
	fmt.Fprintf(os.Stdout, "Saved to: %s\n", result.OutputPath)
	fmt.Fprintf(os.Stdout, "Bytes written: %d\n", result.BytesWritten)

	return nil
}

func resolveOutputPath(requested string, suggestedName string) (string, error) {
	trimmed := strings.TrimSpace(requested)
	if trimmed == "" {
		trimmed = suggestedName
	}

	if stat, err := os.Stat(trimmed); err == nil && stat.IsDir() {
		trimmed = filepath.Join(trimmed, suggestedName)
	}

	trimmed = filepath.Clean(trimmed)
	if dir := filepath.Dir(trimmed); dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return "", fmt.Errorf("create output directory %q: %w", dir, err)
		}
	}

	return trimmed, nil
}
