package main

import (
	"flag"
	"fmt"
	"os"
	"strings"
)

const (
	envPublicBaseURL      = "FBC_PUBLIC_BASE_URL"
	envAdminAPIKey        = "FBC_ADMIN_API_KEY"
	defaultBaseURL        = "http://127.0.0.1:8000"
	defaultUploadChunkRaw = ""
	checksumStatusCode    = 460
)

type CommandConfig struct {
	BaseURL string
	APIKey  string
	JSON    bool
}

func bindCommonFlags(fs *flag.FlagSet, cfg *CommandConfig, includeJSON bool) {
	cfg.BaseURL = strings.TrimSpace(os.Getenv(envPublicBaseURL))
	if cfg.BaseURL == "" {
		cfg.BaseURL = defaultBaseURL
	}

	cfg.APIKey = strings.TrimSpace(os.Getenv(envAdminAPIKey))

	fs.StringVar(&cfg.BaseURL, "host", cfg.BaseURL, fmt.Sprintf("FBC base URL (env %s)", envPublicBaseURL))
	fs.StringVar(&cfg.BaseURL, "base-url", cfg.BaseURL, "Alias for --host")
	fs.StringVar(&cfg.APIKey, "api-key", cfg.APIKey, fmt.Sprintf("Admin API key (env %s)", envAdminAPIKey))

	if includeJSON {
		fs.BoolVar(&cfg.JSON, "json", false, "Print JSON output")
	}
}

func requireNoArgs(fs *flag.FlagSet) error {
	if fs.NArg() == 0 {
		return nil
	}

	return fmt.Errorf("unexpected arguments: %s", strings.Join(fs.Args(), " "))
}

func requireAPIKey(apiKey string) error {
	if strings.TrimSpace(apiKey) != "" {
		return nil
	}

	return fmt.Errorf("--api-key or %s is required for this command", envAdminAPIKey)
}

func setUsage(fs *flag.FlagSet, usageLine string, notes ...string) {
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage: %s\n", usageLine)
		if len(notes) > 0 {
			fmt.Fprintln(fs.Output())
			for _, note := range notes {
				fmt.Fprintln(fs.Output(), note)
			}
		}
		fmt.Fprintln(fs.Output())
		fs.PrintDefaults()
	}
}
