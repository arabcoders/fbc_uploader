package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
	"time"
)

func TestParseByteSize(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		raw   string
		want  int64
		valid bool
	}{
		{name: "bytes", raw: "512", want: 512, valid: true},
		{name: "megabytes", raw: "8M", want: 8 * 1024 * 1024, valid: true},
		{name: "mib", raw: "1MiB", want: 1024 * 1024, valid: true},
		{name: "invalid", raw: "five", valid: false},
	}

	for _, testCase := range tests {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			got, err := parseByteSize(testCase.raw)
			if testCase.valid && err != nil {
				t.Fatalf("parseByteSize(%q) returned error: %v", testCase.raw, err)
			}
			if !testCase.valid && err == nil {
				t.Fatalf("parseByteSize(%q) unexpectedly succeeded", testCase.raw)
			}
			if !testCase.valid {
				return
			}

			if got != testCase.want {
				t.Fatalf("parseByteSize(%q) = %d, want %d", testCase.raw, got, testCase.want)
			}
		})
	}
}

func TestChooseUploadChunkSize(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		configured int64
		tokenMax   int64
		preferred  int64
		want       int64
		wantErr    bool
	}{
		{name: "uses preferred chunk size", configured: 0, tokenMax: 90, preferred: 64, want: 64},
		{name: "falls back to token max", configured: 0, tokenMax: 90, preferred: 0, want: 90},
		{name: "uses explicit override", configured: 32, tokenMax: 90, preferred: 0, want: 32},
		{name: "rejects oversized override", configured: 128, tokenMax: 90, preferred: 0, wantErr: true},
	}

	for _, testCase := range tests {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			got, err := chooseUploadChunkSize(testCase.configured, testCase.tokenMax, testCase.preferred)
			if testCase.wantErr {
				if err == nil {
					t.Fatalf("chooseUploadChunkSize unexpectedly succeeded")
				}
				return
			}

			if err != nil {
				t.Fatalf("chooseUploadChunkSize returned error: %v", err)
			}
			if got != testCase.want {
				t.Fatalf("chooseUploadChunkSize = %d, want %d", got, testCase.want)
			}
		})
	}
}

func TestParseJSONMapSupportsNestedData(t *testing.T) {
	t.Parallel()

	metadata, err := parseJSONMap([]byte(`{"series":{"title":"Episode"},"episode":2}`))
	if err != nil {
		t.Fatalf("parseJSONMap returned error: %v", err)
	}

	series, ok := metadata["series"].(map[string]any)
	if !ok {
		t.Fatalf("nested series metadata was not preserved: %#v", metadata["series"])
	}
	if series["title"] != "Episode" {
		t.Fatalf("series title = %#v, want Episode", series["title"])
	}
}

func TestParseResourceTarget(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name       string
		baseURL    string
		rawURL     string
		wantToken  string
		wantUpload string
	}{
		{
			name:      "share page",
			baseURL:   "https://example.com",
			rawURL:    "https://example.com/f/fbc_abc",
			wantToken: "fbc_abc",
		},
		{
			name:      "upload page",
			baseURL:   "https://example.com",
			rawURL:    "https://example.com/t/upload_abc",
			wantToken: "upload_abc",
		},
		{
			name:       "download route",
			baseURL:    "https://ignored.example",
			rawURL:     "https://media.example/api/tokens/fbc_abc/uploads/upload123/download",
			wantToken:  "fbc_abc",
			wantUpload: "upload123",
		},
		{
			name:       "relative info route",
			baseURL:    "https://example.com",
			rawURL:     "/api/tokens/fbc_abc/uploads/upload123",
			wantToken:  "fbc_abc",
			wantUpload: "upload123",
		},
	}

	for _, testCase := range testCases {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			target, err := parseResourceTarget(testCase.baseURL, testCase.rawURL)
			if err != nil {
				t.Fatalf("parseResourceTarget returned error: %v", err)
			}
			if target.Token != testCase.wantToken {
				t.Fatalf("token = %q, want %q", target.Token, testCase.wantToken)
			}
			if target.UploadID != testCase.wantUpload {
				t.Fatalf("uploadID = %q, want %q", target.UploadID, testCase.wantUpload)
			}
		})
	}
}

func TestLoadCombinedMetadataMergesNestedFlagValues(t *testing.T) {
	t.Parallel()

	metadata, err := loadCombinedMetadata(
		"",
		`{"series":{"title":"Original","season":1},"published":false}`,
		[]string{"series.title=Updated", "series.episode=2", "published=true", "tags=[\"news\",\"sport\"]"},
	)
	if err != nil {
		t.Fatalf("loadCombinedMetadata returned error: %v", err)
	}

	series, ok := metadata["series"].(map[string]any)
	if !ok {
		t.Fatalf("series metadata was not an object: %#v", metadata["series"])
	}
	if got := series["title"]; got != "Updated" {
		t.Fatalf("series.title = %#v, want Updated", got)
	}
	if got := series["season"]; got != json.Number("1") {
		t.Fatalf("series.season = %#v, want json.Number(1)", got)
	}
	if got := series["episode"]; got != int64(2) {
		t.Fatalf("series.episode = %#v, want int64(2)", got)
	}
	if got := metadata["published"]; got != true {
		t.Fatalf("published = %#v, want true", got)
	}

	tags, ok := metadata["tags"].([]any)
	if !ok {
		t.Fatalf("tags metadata was not an array: %#v", metadata["tags"])
	}
	if !reflect.DeepEqual(tags, []any{"news", "sport"}) {
		t.Fatalf("tags = %#v, want [news sport]", tags)
	}
}

func TestLoadCombinedMetadataRejectsPathConflict(t *testing.T) {
	t.Parallel()

	_, err := loadCombinedMetadata("", `{"series":"plain"}`, []string{"series.title=Updated"})
	if err == nil {
		t.Fatalf("loadCombinedMetadata unexpectedly succeeded for conflicting metadata path")
	}
}

func TestMergeMetadataUsesOverlayValues(t *testing.T) {
	t.Parallel()

	merged := mergeMetadata(
		map[string]any{"title": "Auto", "series": map[string]any{"episode": int64(1)}},
		map[string]any{"title": "Manual", "published": true},
	)

	if got := merged["title"]; got != "Manual" {
		t.Fatalf("title = %#v, want Manual", got)
	}
	if got := merged["published"]; got != true {
		t.Fatalf("published = %#v, want true", got)
	}
	series, ok := merged["series"].(map[string]any)
	if !ok {
		t.Fatalf("series was not an object: %#v", merged["series"])
	}
	if got := series["episode"]; got != int64(1) {
		t.Fatalf("series.episode = %#v, want int64(1)", got)
	}
}

func TestClientExtractMetadata(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s, want POST", r.Method)
		}
		if r.URL.Path != "/api/metadata/extract" {
			t.Fatalf("path = %s, want /api/metadata/extract", r.URL.Path)
		}

		raw, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("ReadAll returned error: %v", err)
		}

		var payload MetadataExtractRequest
		if err := json.Unmarshal(raw, &payload); err != nil {
			t.Fatalf("json.Unmarshal returned error: %v", err)
		}
		if payload.Filename != "example.mp4" {
			t.Fatalf("filename = %q, want example.mp4", payload.Filename)
		}

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"metadata":{"title":"Example Show"}}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "")
	if err != nil {
		t.Fatalf("NewClient returned error: %v", err)
	}

	metadata, err := client.ExtractMetadata(context.Background(), "example.mp4")
	if err != nil {
		t.Fatalf("ExtractMetadata returned error: %v", err)
	}
	if !reflect.DeepEqual(metadata, map[string]any{"title": "Example Show"}) {
		t.Fatalf("metadata = %#v, want map[title:Example Show]", metadata)
	}
}

func TestClientCompleteUploadOmitsTokenQuery(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s, want POST", r.Method)
		}
		if r.URL.Path != "/api/uploads/upload123/complete" {
			t.Fatalf("path = %s, want /api/uploads/upload123/complete", r.URL.Path)
		}
		if got := r.URL.RawQuery; got != "" {
			t.Fatalf("query = %q, want empty", got)
		}

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"public_id":"upload123","meta_data":{},"upload_offset":0,"status":"completed","created_at":"2026-05-02T16:37:12Z"}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "")
	if err != nil {
		t.Fatalf("NewClient returned error: %v", err)
	}

	record, err := client.CompleteUpload(context.Background(), "upload123")
	if err != nil {
		t.Fatalf("CompleteUpload returned error: %v", err)
	}
	if record.PublicID != "upload123" {
		t.Fatalf("public_id = %q, want upload123", record.PublicID)
	}
	if record.Status != "completed" {
		t.Fatalf("status = %q, want completed", record.Status)
	}
	if record.MetaData == nil {
		t.Fatalf("meta_data should decode to an empty map, got nil")
	}
	if len(record.MetaData) != 0 {
		t.Fatalf("meta_data = %#v, want empty map", record.MetaData)
	}
	if record.UploadOffset != 0 {
		t.Fatalf("upload_offset = %d, want 0", record.UploadOffset)
	}
	if record.CreatedAt.Time.IsZero() {
		t.Fatalf("created_at should decode, got zero time")
	}
}

func TestFlexibleTimeUnmarshalAcceptsNaiveAndRFC3339(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name     string
		raw      string
		wantTime time.Time
	}{
		{
			name:     "naive",
			raw:      `"2026-05-02T16:37:12"`,
			wantTime: time.Date(2026, 5, 2, 16, 37, 12, 0, time.UTC),
		},
		{
			name:     "rfc3339 zulu",
			raw:      `"2026-05-02T16:37:12Z"`,
			wantTime: time.Date(2026, 5, 2, 16, 37, 12, 0, time.UTC),
		},
		{
			name:     "rfc3339 offset",
			raw:      `"2026-05-02T18:37:12+02:00"`,
			wantTime: time.Date(2026, 5, 2, 18, 37, 12, 0, time.FixedZone("", 2*60*60)),
		},
	}

	for _, testCase := range testCases {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			var parsed FlexibleTime
			if err := json.Unmarshal([]byte(testCase.raw), &parsed); err != nil {
				t.Fatalf("json.Unmarshal(%s) returned error: %v", testCase.raw, err)
			}

			if !parsed.Time.Equal(testCase.wantTime) {
				t.Fatalf("parsed time = %s, want %s", parsed.Time.Format(time.RFC3339Nano), testCase.wantTime.Format(time.RFC3339Nano))
			}
		})
	}
}
