package main

import "time"

type TokenResponse struct {
	Token         string       `json:"token"`
	DownloadToken string       `json:"download_token"`
	UploadURL     string       `json:"upload_url"`
	ExpiresAt     FlexibleTime `json:"expires_at"`
	MaxUploads    int          `json:"max_uploads"`
	MaxSizeBytes  int64        `json:"max_size_bytes"`
	AllowedMime   []string     `json:"allowed_mime"`
}

type TokenPublicInfo struct {
	Token                *string         `json:"token"`
	DownloadToken        string          `json:"download_token"`
	RemainingUploads     int             `json:"remaining_uploads"`
	MaxUploads           int             `json:"max_uploads"`
	MaxSizeBytes         int64           `json:"max_size_bytes"`
	MaxChunkBytes        int64           `json:"max_chunk_bytes"`
	AllowedMime          []string        `json:"allowed_mime"`
	ExpiresAt            FlexibleTime    `json:"expires_at"`
	Disabled             bool            `json:"disabled"`
	AllowPublicDownloads bool            `json:"allow_public_downloads"`
	Uploads              []UploadRecord  `json:"uploads"`
}

type UploadRecord struct {
	PublicID              string         `json:"public_id"`
	Filename              *string        `json:"filename"`
	Ext                   *string        `json:"ext"`
	Mimetype              *string        `json:"mimetype"`
	SizeBytes             *int64         `json:"size_bytes"`
	MetaData              map[string]any `json:"meta_data"`
	UploadLength          *int64         `json:"upload_length"`
	UploadOffset          int64          `json:"upload_offset"`
	RecommendedChunkBytes *int64         `json:"recommended_chunk_bytes"`
	Status                string         `json:"status"`
	CreatedAt             FlexibleTime   `json:"created_at"`
	CompletedAt           *FlexibleTime  `json:"completed_at"`
	DownloadURL           *string        `json:"download_url"`
	StreamURL             *string        `json:"stream_url"`
	UploadURL             *string        `json:"upload_url"`
	InfoURL               *string        `json:"info_url"`
}

type InitiateUploadResponse struct {
	UploadID              string         `json:"upload_id"`
	UploadURL             string         `json:"upload_url"`
	DownloadURL           string         `json:"download_url"`
	MetaData              map[string]any `json:"meta_data"`
	AllowedMime           []string       `json:"allowed_mime"`
	RemainingUploads      int            `json:"remaining_uploads"`
	RecommendedChunkBytes int64          `json:"recommended_chunk_bytes"`
}

type CreateTokenRequest struct {
	MaxUploads     int        `json:"max_uploads"`
	MaxSizeBytes   int64      `json:"max_size_bytes"`
	ExpiryDatetime *time.Time `json:"expiry_datetime,omitempty"`
	AllowedMime    []string   `json:"allowed_mime,omitempty"`
}

type UploadRequest struct {
	MetaData  map[string]any `json:"meta_data"`
	Filename  string         `json:"filename,omitempty"`
	Filetype  string         `json:"filetype,omitempty"`
	SizeBytes int64          `json:"size_bytes"`
}

type MetadataExtractRequest struct {
	Filename string `json:"filename"`
}

type MetadataExtractResponse struct {
	Metadata map[string]any `json:"metadata"`
}

type CancelResponse struct {
	Message          string `json:"message"`
	RemainingUploads int    `json:"remaining_uploads"`
}

type HeadUploadInfo struct {
	Offset int64 `json:"offset"`
	Length int64 `json:"length"`
}

type CreateCommandResult struct {
	Token         string       `json:"token"`
	DownloadToken string       `json:"download_token"`
	UploadPageURL string       `json:"upload_page_url"`
	ShareURL      string       `json:"share_url"`
	ExpiresAt     FlexibleTime `json:"expires_at"`
	MaxUploads    int          `json:"max_uploads"`
	MaxSizeBytes  int64        `json:"max_size_bytes"`
	AllowedMime   []string     `json:"allowed_mime,omitempty"`
}

type UploadCommandResult struct {
	UploadID              string       `json:"upload_id"`
	DownloadToken         string       `json:"download_token"`
	InfoURL               string       `json:"info_url"`
	DownloadURL           string       `json:"download_url"`
	ResumedFrom           int64        `json:"resumed_from"`
	ChunkSizeBytes        int64        `json:"chunk_size_bytes"`
	RecommendedChunkBytes int64        `json:"recommended_chunk_bytes"`
	Record                UploadRecord `json:"record"`
}

type DownloadCommandResult struct {
	UploadID      string `json:"upload_id"`
	DownloadToken string `json:"download_token"`
	OutputPath    string `json:"output_path,omitempty"`
	Filename      string `json:"filename"`
	BytesWritten  int64  `json:"bytes_written"`
}

type CancelCommandResult struct {
	UploadID         string `json:"upload_id"`
	Message          string `json:"message"`
	RemainingUploads int    `json:"remaining_uploads"`
}

type ResourceTarget struct {
	BaseURL  string
	Token    string
	UploadID string
}
