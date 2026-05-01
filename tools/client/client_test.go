package main

import (
	"encoding/json"
	"reflect"
	"testing"
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
