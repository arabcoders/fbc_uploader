package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

type Client struct {
	BaseURL *url.URL
	HTTP    *http.Client
	APIKey  string
}

type HTTPError struct {
	StatusCode int
	Method     string
	URL        string
	Detail     string
}

func (e *HTTPError) Error() string {
	if strings.TrimSpace(e.Detail) == "" {
		return fmt.Sprintf("%s %s failed with status %d", e.Method, e.URL, e.StatusCode)
	}

	return fmt.Sprintf("%s %s failed with status %d: %s", e.Method, e.URL, e.StatusCode, e.Detail)
}

func NewClient(baseURL string, apiKey string) (*Client, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil {
		return nil, err
	}

	return &Client{
		BaseURL: parsed,
		HTTP:    &http.Client{},
		APIKey:  strings.TrimSpace(apiKey),
	}, nil
}

func parseBaseURL(raw string) (*url.URL, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		value = defaultBaseURL
	}

	if !strings.Contains(value, "://") {
		value = "http://" + value
	}

	parsed, err := url.Parse(value)
	if err != nil {
		return nil, fmt.Errorf("parse base URL %q: %w", raw, err)
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("base URL must include scheme and host")
	}

	parsed.Path = strings.TrimRight(parsed.Path, "/")
	parsed.RawPath = ""
	parsed.RawQuery = ""
	parsed.Fragment = ""

	return parsed, nil
}

func (c *Client) ResolveReference(raw string) (*url.URL, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil, fmt.Errorf("URL cannot be empty")
	}

	ref, err := url.Parse(value)
	if err != nil {
		return nil, fmt.Errorf("parse URL %q: %w", raw, err)
	}
	if ref.IsAbs() {
		return ref, nil
	}

	resolved := *c.BaseURL
	resolved.Path = joinURLPath(c.BaseURL.Path, ref.Path)
	resolved.RawPath = ""
	resolved.RawQuery = ref.RawQuery
	resolved.Fragment = ref.Fragment

	return &resolved, nil
}

func (c *Client) ResolveString(raw string) string {
	resolved, err := c.ResolveReference(raw)
	if err != nil {
		return raw
	}

	return resolved.String()
}

func (c *Client) do(ctx context.Context, method string, rawURL string, query url.Values, headers map[string]string, body io.Reader) (*http.Response, error) {
	requestURL, err := c.ResolveReference(rawURL)
	if err != nil {
		return nil, err
	}

	values := requestURL.Query()
	for key, items := range query {
		for _, item := range items {
			values.Add(key, item)
		}
	}
	requestURL.RawQuery = values.Encode()

	req, err := http.NewRequestWithContext(ctx, method, requestURL.String(), body)
	if err != nil {
		return nil, err
	}

	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}

	return resp, nil
}

func (c *Client) doJSON(ctx context.Context, method string, rawURL string, query url.Values, payload any, out any) error {
	var body io.Reader
	headers := map[string]string{}
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return fmt.Errorf("encode request body: %w", err)
		}
		body = bytes.NewReader(encoded)
		headers["Content-Type"] = "application/json"
	}

	resp, err := c.do(ctx, method, rawURL, query, headers, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return parseHTTPError(resp)
	}

	if out == nil {
		_, _ = io.Copy(io.Discard, resp.Body)
		return nil
	}

	decoder := json.NewDecoder(resp.Body)
	if err := decoder.Decode(out); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	return nil
}

func parseHTTPError(resp *http.Response) error {
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	detail := strings.TrimSpace(string(raw))

	var envelope map[string]any
	if len(raw) > 0 && json.Unmarshal(raw, &envelope) == nil {
		if value, ok := envelope["detail"]; ok {
			detail = stringifyJSONValue(value)
		}
	}
	if detail == "" {
		detail = resp.Status
	}

	return &HTTPError{
		StatusCode: resp.StatusCode,
		Method:     resp.Request.Method,
		URL:        resp.Request.URL.String(),
		Detail:     detail,
	}
}

func stringifyJSONValue(value any) string {
	if str, ok := value.(string); ok {
		return str
	}

	encoded, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprintf("%v", value)
	}

	return string(encoded)
}

func tokenInfoPath(token string) string {
	return "/api/tokens/" + url.PathEscape(token)
}

func uploadTusPath(uploadID string) string {
	return "/api/uploads/" + url.PathEscape(uploadID) + "/tus"
}

func fileInfoPath(downloadToken string, uploadID string) string {
	return "/api/tokens/" + url.PathEscape(downloadToken) + "/uploads/" + url.PathEscape(uploadID)
}

func fileDownloadPath(downloadToken string, uploadID string) string {
	return fileInfoPath(downloadToken, uploadID) + "/download"
}

func sharePath(downloadToken string) string {
	return "/f/" + url.PathEscape(downloadToken)
}

func uploadPagePath(uploadToken string) string {
	return "/t/" + url.PathEscape(uploadToken)
}

func (c *Client) CreateToken(ctx context.Context, payload CreateTokenRequest) (TokenResponse, error) {
	var response TokenResponse
	err := c.doJSON(ctx, http.MethodPost, "/api/tokens/", nil, payload, &response)
	return response, err
}

func (c *Client) GetTokenInfo(ctx context.Context, token string) (TokenPublicInfo, error) {
	var response TokenPublicInfo
	err := c.doJSON(ctx, http.MethodGet, tokenInfoPath(token), nil, nil, &response)
	return response, err
}

func (c *Client) GetFileInfo(ctx context.Context, downloadToken string, uploadID string) (UploadRecord, error) {
	var response UploadRecord
	err := c.doJSON(ctx, http.MethodGet, fileInfoPath(downloadToken, uploadID), nil, nil, &response)
	return response, err
}

func (c *Client) InitiateUpload(ctx context.Context, token string, payload UploadRequest) (InitiateUploadResponse, error) {
	var response InitiateUploadResponse
	query := url.Values{"token": []string{token}}
	err := c.doJSON(ctx, http.MethodPost, "/api/uploads/initiate", query, payload, &response)
	return response, err
}

func (c *Client) ExtractMetadata(ctx context.Context, filename string) (map[string]any, error) {
	var response MetadataExtractResponse
	err := c.doJSON(ctx, http.MethodPost, "/api/metadata/extract", nil, MetadataExtractRequest{Filename: filename}, &response)
	if err != nil {
		return nil, err
	}
	if response.Metadata == nil {
		return map[string]any{}, nil
	}

	return response.Metadata, nil
}

func (c *Client) CompleteUpload(ctx context.Context, uploadID string, token string) (UploadRecord, error) {
	var response UploadRecord
	query := url.Values{"token": []string{token}}
	err := c.doJSON(ctx, http.MethodPost, "/api/uploads/"+url.PathEscape(uploadID)+"/complete", query, nil, &response)
	return response, err
}

func (c *Client) CancelUpload(ctx context.Context, uploadID string, token string) (CancelResponse, error) {
	var response CancelResponse
	query := url.Values{"token": []string{token}}
	err := c.doJSON(ctx, http.MethodDelete, "/api/uploads/"+url.PathEscape(uploadID)+"/cancel", query, nil, &response)
	return response, err
}

func (c *Client) HeadUpload(ctx context.Context, uploadID string) (HeadUploadInfo, error) {
	resp, err := c.do(ctx, http.MethodHead, uploadTusPath(uploadID), nil, nil, nil)
	if err != nil {
		return HeadUploadInfo{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return HeadUploadInfo{}, parseHTTPError(resp)
	}

	offset, err := parseIntHeader(resp.Header.Get("Upload-Offset"), "Upload-Offset")
	if err != nil {
		return HeadUploadInfo{}, err
	}

	length, err := parseIntHeader(resp.Header.Get("Upload-Length"), "Upload-Length")
	if err != nil {
		return HeadUploadInfo{}, err
	}

	return HeadUploadInfo{Offset: offset, Length: length}, nil
}

func (c *Client) PatchUpload(ctx context.Context, uploadID string, offset int64, chunk []byte, checksum string) (HeadUploadInfo, error) {
	headers := map[string]string{
		"Content-Type":    "application/offset+octet-stream",
		"Upload-Offset":   strconv.FormatInt(offset, 10),
		"Content-Length":  strconv.Itoa(len(chunk)),
		"Upload-Checksum": checksum,
	}

	resp, err := c.do(ctx, http.MethodPatch, uploadTusPath(uploadID), nil, headers, bytes.NewReader(chunk))
	if err != nil {
		return HeadUploadInfo{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return HeadUploadInfo{}, parseHTTPError(resp)
	}

	newOffset, err := parseIntHeader(resp.Header.Get("Upload-Offset"), "Upload-Offset")
	if err != nil {
		return HeadUploadInfo{}, err
	}

	length := int64(-1)
	if rawLength := strings.TrimSpace(resp.Header.Get("Upload-Length")); rawLength != "" {
		length, err = parseIntHeader(rawLength, "Upload-Length")
		if err != nil {
			return HeadUploadInfo{}, err
		}
	}

	return HeadUploadInfo{Offset: newOffset, Length: length}, nil
}

func (c *Client) DownloadFile(ctx context.Context, downloadToken string, uploadID string, writer io.Writer) (int64, error) {
	resp, err := c.do(ctx, http.MethodGet, fileDownloadPath(downloadToken, uploadID), nil, nil, nil)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return 0, parseHTTPError(resp)
	}

	return io.Copy(writer, resp.Body)
}

func parseIntHeader(raw string, headerName string) (int64, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return 0, fmt.Errorf("missing %s header", headerName)
	}

	value, err := strconv.ParseInt(trimmed, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("invalid %s header %q: %w", headerName, raw, err)
	}

	return value, nil
}

func parseResourceTarget(baseURL string, raw string) (ResourceTarget, error) {
	client, err := NewClient(baseURL, "")
	if err != nil {
		return ResourceTarget{}, err
	}

	resolved, err := client.ResolveReference(raw)
	if err != nil {
		return ResourceTarget{}, err
	}

	parts := splitPath(resolved.Path)
	for idx := 0; idx < len(parts); idx++ {
		if idx+1 < len(parts) && (parts[idx] == "f" || parts[idx] == "t") {
			return ResourceTarget{
				BaseURL: buildBaseURLString(resolved, parts[:idx]),
				Token:   parts[idx+1],
			}, nil
		}

		if idx+2 < len(parts) && parts[idx] == "api" && parts[idx+1] == "tokens" {
			target := ResourceTarget{
				BaseURL: buildBaseURLString(resolved, parts[:idx]),
				Token:   parts[idx+2],
			}
			if idx+4 < len(parts) && parts[idx+3] == "uploads" {
				target.UploadID = parts[idx+4]
			}
			return target, nil
		}
	}

	return ResourceTarget{}, fmt.Errorf("unsupported FBC URL %q", raw)
}

func splitPath(raw string) []string {
	trimmed := strings.Trim(raw, "/")
	if trimmed == "" {
		return nil
	}

	return strings.Split(trimmed, "/")
}

func joinURLPath(prefix string, suffix string) string {
	left := strings.TrimRight(prefix, "/")
	right := strings.TrimLeft(suffix, "/")

	switch {
	case left == "" && right == "":
		return "/"
	case left == "":
		return "/" + right
	case right == "":
		return left
	default:
		return left + "/" + right
	}
}

func buildBaseURLString(resolved *url.URL, prefixParts []string) string {
	base := *resolved
	base.RawQuery = ""
	base.Fragment = ""
	if len(prefixParts) == 0 {
		base.Path = ""
		base.RawPath = ""
		return strings.TrimRight(base.String(), "/")
	}

	base.Path = "/" + strings.Join(prefixParts, "/")
	base.RawPath = ""
	return strings.TrimRight(base.String(), "/")
}
