package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

type FlexibleTime struct {
	time.Time
}

var acceptedTimeLayouts = []string{
	time.RFC3339Nano,
	time.RFC3339,
	"2006-01-02T15:04:05.999999",
	"2006-01-02T15:04:05",
}

func (t *FlexibleTime) UnmarshalJSON(data []byte) error {
	trimmed := strings.TrimSpace(string(data))
	if trimmed == "null" {
		t.Time = time.Time{}
		return nil
	}

	var raw string
	if err := json.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("expected JSON string timestamp: %w", err)
	}

	parsed, err := parseFlexibleTime(raw)
	if err != nil {
		return err
	}

	t.Time = parsed
	return nil
}

func (t FlexibleTime) MarshalJSON() ([]byte, error) {
	if t.Time.IsZero() {
		return []byte("null"), nil
	}

	return json.Marshal(t.Time.Format(time.RFC3339))
}

func parseFlexibleTime(raw string) (time.Time, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return time.Time{}, fmt.Errorf("timestamp cannot be empty")
	}

	for _, layout := range acceptedTimeLayouts {
		parsed, err := time.Parse(layout, trimmed)
		if err == nil {
			if parsed.Location() == time.UTC || strings.HasSuffix(trimmed, "Z") || strings.ContainsAny(trimmed, "+-") {
				return parsed, nil
			}
			return time.Date(parsed.Year(), parsed.Month(), parsed.Day(), parsed.Hour(), parsed.Minute(), parsed.Second(), parsed.Nanosecond(), time.UTC), nil
		}
	}

	return time.Time{}, fmt.Errorf("unsupported timestamp format %q", raw)
}
