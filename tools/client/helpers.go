package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"mime"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type stringListFlag []string

type metadataFlag []string

func (f *stringListFlag) String() string {
	return strings.Join(*f, ",")
}

func (f *stringListFlag) Set(value string) error {
	for _, item := range strings.Split(value, ",") {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		*f = append(*f, trimmed)
	}

	return nil
}

func (f *metadataFlag) String() string {
	return strings.Join(*f, ",")
}

func (f *metadataFlag) Set(value string) error {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return fmt.Errorf("metadata entry cannot be empty")
	}

	*f = append(*f, trimmed)
	return nil
}

func printJSON(w io.Writer, value any) error {
	encoder := json.NewEncoder(w)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}

func parseJSONMap(raw []byte) (map[string]any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()

	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}

	metadata, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("metadata must be a JSON object")
	}

	return metadata, nil
}

func loadMetadata(metadataFile string, metadataJSON string) (map[string]any, error) {
	if strings.TrimSpace(metadataFile) != "" && strings.TrimSpace(metadataJSON) != "" {
		return nil, fmt.Errorf("use only one of --metadata-file or --metadata-json")
	}

	if strings.TrimSpace(metadataJSON) != "" {
		metadata, err := parseJSONMap([]byte(metadataJSON))
		if err != nil {
			return nil, fmt.Errorf("parse --metadata-json: %w", err)
		}

		return metadata, nil
	}

	if strings.TrimSpace(metadataFile) == "" {
		return map[string]any{}, nil
	}

	raw, err := os.ReadFile(metadataFile)
	if err != nil {
		return nil, fmt.Errorf("read metadata file %q: %w", metadataFile, err)
	}

	metadata, err := parseJSONMap(raw)
	if err != nil {
		return nil, fmt.Errorf("parse metadata file %q: %w", metadataFile, err)
	}

	return metadata, nil
}

func loadCombinedMetadata(metadataFile string, metadataJSON string, metadataEntries []string) (map[string]any, error) {
	metadata, err := loadMetadata(metadataFile, metadataJSON)
	if err != nil {
		return nil, err
	}

	if len(metadataEntries) == 0 {
		return metadata, nil
	}

	merged := cloneMap(metadata)
	for _, entry := range metadataEntries {
		keyPath, value, err := parseMetadataEntry(entry)
		if err != nil {
			return nil, err
		}
		if err := assignMetadataValue(merged, keyPath, value); err != nil {
			return nil, err
		}
	}

	return merged, nil
}

func mergeMetadata(base map[string]any, overlay map[string]any) map[string]any {
	if len(base) == 0 && len(overlay) == 0 {
		return map[string]any{}
	}

	merged := cloneMap(base)
	for key, value := range overlay {
		merged[key] = cloneValue(value)
	}

	return merged
}

func parseMetadataEntry(entry string) ([]string, any, error) {
	parts := strings.SplitN(entry, "=", 2)
	if len(parts) != 2 {
		return nil, nil, fmt.Errorf("metadata entry %q must use key=value", entry)
	}

	key := strings.TrimSpace(parts[0])
	if key == "" {
		return nil, nil, fmt.Errorf("metadata entry %q is missing a key", entry)
	}

	rawPath := strings.Split(key, ".")
	keyPath := make([]string, 0, len(rawPath))
	for _, part := range rawPath {
		trimmed := strings.TrimSpace(part)
		if trimmed == "" {
			return nil, nil, fmt.Errorf("metadata key %q contains an empty path segment", key)
		}
		keyPath = append(keyPath, trimmed)
	}

	value, err := parseMetadataScalar(parts[1])
	if err != nil {
		return nil, nil, fmt.Errorf("metadata %q: %w", key, err)
	}

	return keyPath, value, nil
}

func parseMetadataScalar(raw string) (any, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "", nil
	}

	if value, ok, err := tryParseJSONObjectOrArray(trimmed); err != nil {
		return nil, err
	} else if ok {
		return value, nil
	}

	if trimmed == "null" {
		return nil, nil
	}
	if trimmed == "true" {
		return true, nil
	}
	if trimmed == "false" {
		return false, nil
	}

	if strings.HasPrefix(trimmed, "\"") && strings.HasSuffix(trimmed, "\"") {
		unquoted, err := strconv.Unquote(trimmed)
		if err == nil {
			return unquoted, nil
		}
	}

	if !strings.ContainsAny(trimmed, " \\t\\n\\r") {
		if integer, err := strconv.ParseInt(trimmed, 10, 64); err == nil {
			return integer, nil
		}
		if number, err := strconv.ParseFloat(trimmed, 64); err == nil && !math.IsInf(number, 0) && !math.IsNaN(number) {
			return number, nil
		}
	}

	return raw, nil
}

func tryParseJSONObjectOrArray(raw string) (any, bool, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil, false, nil
	}

	startsObject := strings.HasPrefix(trimmed, "{") && strings.HasSuffix(trimmed, "}")
	startsArray := strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]")
	if !startsObject && !startsArray {
		return nil, false, nil
	}

	decoder := json.NewDecoder(strings.NewReader(trimmed))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, false, fmt.Errorf("invalid JSON value %q: %w", raw, err)
	}

	return value, true, nil
}

func assignMetadataValue(root map[string]any, keyPath []string, value any) error {
	current := root
	for idx, key := range keyPath[:len(keyPath)-1] {
		existing, ok := current[key]
		if !ok {
			next := map[string]any{}
			current[key] = next
			current = next
			continue
		}

		next, ok := existing.(map[string]any)
		if !ok {
			return fmt.Errorf("metadata path %q conflicts with non-object value at %q", strings.Join(keyPath, "."), strings.Join(keyPath[:idx+1], "."))
		}
		current = next
	}

	leaf := keyPath[len(keyPath)-1]
	if existing, ok := current[leaf]; ok {
		if _, isMap := existing.(map[string]any); isMap {
			if _, incomingIsMap := value.(map[string]any); !incomingIsMap {
				return fmt.Errorf("metadata path %q conflicts with an existing object value", strings.Join(keyPath, "."))
			}
		}
	}
	current[leaf] = value
	return nil
}

func cloneMap(source map[string]any) map[string]any {
	if source == nil {
		return map[string]any{}
	}

	cloned := make(map[string]any, len(source))
	for key, value := range source {
		cloned[key] = cloneValue(value)
	}
	return cloned
}

func cloneValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneMap(typed)
	case []any:
		items := make([]any, len(typed))
		for idx, item := range typed {
			items[idx] = cloneValue(item)
		}
		return items
	default:
		return typed
	}
}

func normalizeDeclaredMIME(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}

	mediaType, _, err := mime.ParseMediaType(trimmed)
	if err == nil {
		return strings.ToLower(mediaType)
	}

	return strings.ToLower(trimmed)
}

func detectDeclaredMIME(filePath string, override string) string {
	if normalized := normalizeDeclaredMIME(override); normalized != "" {
		return normalized
	}

	guessed := mime.TypeByExtension(strings.ToLower(filepath.Ext(filePath)))
	return normalizeDeclaredMIME(guessed)
}

func sanitizeFilename(name string, fallback string) string {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		trimmed = fallback
	}

	base := filepath.Base(trimmed)
	base = strings.TrimSpace(base)
	if base == "" || base == "." || base == string(filepath.Separator) {
		return fallback
	}

	return base
}

func parseExpiry(value string) (time.Time, error) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return time.Time{}, fmt.Errorf("expiry cannot be empty")
	}

	if parsed, err := time.Parse(time.RFC3339, trimmed); err == nil {
		return parsed, nil
	}

	parsed, err := time.Parse("2006-01-02", trimmed)
	if err != nil {
		return time.Time{}, fmt.Errorf("expiry must be RFC3339 or YYYY-MM-DD")
	}

	return parsed.UTC(), nil
}

func selectCompletedUpload(info TokenPublicInfo) (UploadRecord, error) {
	completed := make([]UploadRecord, 0, len(info.Uploads))
	for _, upload := range info.Uploads {
		if upload.Status == "completed" {
			completed = append(completed, upload)
		}
	}

	switch len(completed) {
	case 0:
		return UploadRecord{}, fmt.Errorf("token %q has no completed uploads", info.DownloadToken)
	case 1:
		return completed[0], nil
	default:
		ids := make([]string, 0, len(completed))
		for _, upload := range completed {
			ids = append(ids, upload.PublicID)
		}

		return UploadRecord{}, fmt.Errorf("token %q has multiple completed uploads (%s); use --upload-id", info.DownloadToken, strings.Join(ids, ", "))
	}
}

func formatBytes(size int64) string {
	const unit = 1024
	if size < unit {
		return fmt.Sprintf("%d B", size)
	}

	div, exp := int64(unit), 0
	for n := size / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}

	return fmt.Sprintf("%.1f %ciB", float64(size)/float64(div), "KMGTPE"[exp])
}

func intFromInt64(value int64, fieldName string) (int, error) {
	maxInt := int64(^uint(0) >> 1)
	if value < 0 || value > maxInt {
		return 0, fmt.Errorf("%s=%d is out of range on this platform", fieldName, value)
	}

	return int(value), nil
}
