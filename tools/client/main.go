package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := run(ctx, os.Args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return
		}

		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string) error {
	if len(args) == 0 {
		printRootUsage(os.Stdout)
		return flag.ErrHelp
	}

	switch args[0] {
	case "create":
		return runCreateCommand(ctx, args[1:])
	case "info":
		return runInfoCommand(ctx, args[1:])
	case "upload":
		return runUploadCommand(ctx, args[1:])
	case "download":
		return runDownloadCommand(ctx, args[1:])
	case "cancel":
		return runCancelCommand(ctx, args[1:])
	case "help", "-h", "--help":
		printRootUsage(os.Stdout)
		return flag.ErrHelp
	default:
		printRootUsage(os.Stderr)
		return fmt.Errorf("unknown command %q", args[0])
	}
}

func printRootUsage(w *os.File) {
	fmt.Fprintln(w, "fbc is a standard-library CLI for FBC Uploader.")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Usage:")
	fmt.Fprintln(w, "  fbc <command> [options]")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Commands:")
	fmt.Fprintln(w, "  create    Create an upload/download token pair")
	fmt.Fprintln(w, "  info      Inspect a token or a specific uploaded file")
	fmt.Fprintln(w, "  upload    Upload a file with server-driven resume")
	fmt.Fprintln(w, "  download  Download a completed uploaded file")
	fmt.Fprintln(w, "  cancel    Cancel an incomplete upload")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Environment:")
	fmt.Fprintf(w, "  %s   Default FBC base URL\n", envPublicBaseURL)
	fmt.Fprintf(w, "  %s   Admin API key for restricted routes\n", envAdminAPIKey)
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Run `fbc <command> --help` for command-specific options.")
}
