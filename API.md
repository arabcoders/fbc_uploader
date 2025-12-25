# HTTP API Documentation

This document describes the FBC Uploader REST API endpoints. All endpoints return JSON responses unless otherwise specified. The API implements token-based authentication and TUS protocol for resumable file uploads.

> **Note**: All API routes are prefixed with `/api`. For deployment and environment configuration, see [README.md](README.md).

---

## Table of Contents

- [HTTP API Documentation](#http-api-documentation)
  - [Table of Contents](#table-of-contents)
  - [Authentication](#authentication)
    - [Admin Authentication](#admin-authentication)
    - [Public Endpoints](#public-endpoints)
  - [Global Notes](#global-notes)
  - [Endpoints](#endpoints)
    - [GET /health](#get-health)
    - [POST /api/tokens/](#post-apitokens)
    - [GET /api/tokens/](#get-apitokens)
    - [GET /api/tokens/{token\_value}](#get-apitokenstoken_value)
    - [PATCH /api/tokens/{token\_value}](#patch-apitokenstoken_value)
    - [DELETE /api/tokens/{token\_value}](#delete-apitokenstoken_value)
    - [GET /api/tokens/{token\_value}/info](#get-apitokenstoken_valueinfo)
    - [GET /api/tokens/{token\_value}/uploads](#get-apitokenstoken_valueuploads)
    - [GET /api/tokens/{download\_token}/uploads/{upload\_id}](#get-apitokensdownload_tokenuploadsupload_id)
    - [POST /api/uploads/initiate](#post-apiuploadsinitiate)
    - [OPTIONS /api/uploads/tus](#options-apiuploadstus)
    - [HEAD /api/uploads/{upload\_id}/tus](#head-apiuploadsupload_idtus)
    - [PATCH /api/uploads/{upload\_id}/tus](#patch-apiuploadsupload_idtus)
    - [DELETE /api/uploads/{upload\_id}/tus](#delete-apiuploadsupload_idtus)
    - [DELETE /api/uploads/{upload\_id}/cancel](#delete-apiuploadsupload_idcancel)
    - [POST /api/uploads/{upload\_id}/complete](#post-apiuploadsupload_idcomplete)
    - [GET /api/metadata/](#get-apimetadata)
    - [POST /api/metadata/validate](#post-apimetadatavalidate)
    - [GET /api/notice/](#get-apinotice)
    - [GET /api/admin/validate](#get-apiadminvalidate)
    - [DELETE /api/admin/uploads/{upload\_id}](#delete-apiadminuploadsupload_id)
  - [TUS Protocol](#tus-protocol)
  - [Upload Flow](#upload-flow)
  - [Error Codes Reference](#error-codes-reference)
  - [Notes](#notes)

---

## Authentication

### Admin Authentication

Admin-only endpoints require a Bearer token in the `Authorization` header:

```http
Authorization: Bearer <admin_api_key>
```

The admin API key is configured via `FBC_ADMIN_API_KEY` environment variable or auto-generated and stored in `{config_path}/secret.key`.

### Public Endpoints

The following endpoints are always public:
- `GET /health`
- `GET /api/tokens/{token}/info`
- `POST /api/uploads/initiate?token=...`
- All TUS protocol endpoints (`/api/uploads/{id}/tus`)
- `GET /api/metadata/`
- `POST /api/metadata/validate`
- `GET /api/notice/`

When `FBC_ALLOW_PUBLIC_DOWNLOADS=1`, download endpoints also become public without requiring admin authentication.

---

## Global Notes

- **Content-Type**
  - Requests with JSON body should include `Content-Type: application/json`
  - TUS protocol PATCH requests require `Content-Type: application/offset+octet-stream`
  - Responses typically include `Content-Type: application/json`, unless returning a file

- **Status Codes**
  - `200 OK` - Request successful
  - `201 Created` - Resource created successfully
  - `204 No Content` - Request successful, no content to return
  - `4xx` - Client errors (bad request, unauthorized, forbidden, not found)
  - `5xx` - Server errors

- **Error Responses**
  When an error occurs, responses follow this structure:
  ```json
  {
    "detail": "Error description"
  }
  ```
  or for validation errors:
  ```json
  {
    "detail": {
      "field": "field_name",
      "message": "Error message"
    }
  }
  ```

- **Datetime Format**
  All datetime values are in UTC with ISO 8601 format including timezone info.

---

## Endpoints

### GET /health

Health check endpoint to verify the service is running.

**Authentication:** None

**Response (200):**
```json
{
  "status": "ok"
}
```

---

### POST /api/tokens/

Create a new upload token.

**Authentication:** Required (Admin)

**Request Body:**
```json
{
  "max_uploads": 5,
  "max_size_bytes": 104857600,
  "expiry_datetime": "2025-12-24T00:00:00Z",
  "allowed_mime": ["application/pdf", "video/*"]
}
```

**Fields:**
- `max_uploads` (integer, required): Maximum number of uploads allowed (min: 1)
- `max_size_bytes` (integer, required): Maximum file size in bytes (> 0)
- `expiry_datetime` (datetime, optional): Token expiration date (defaults to current time + `FBC_DEFAULT_TOKEN_TTL_HOURS`)
- `allowed_mime` (array of strings, optional): Allowed MIME types with wildcard support (e.g., `video/*`). Empty = all types allowed

**Response (201):**
```json
{
  "token": "upload-token-string",
  "download_token": "fbc_download-token-string",
  "upload_url": "http://localhost:8000/api/uploads/initiate?token=upload-token-string",
  "expires_at": "2025-12-24T00:00:00Z",
  "max_uploads": 5,
  "max_size_bytes": 104857600,
  "allowed_mime": ["application/pdf", "video/*"]
}
```

---

### GET /api/tokens/

List all upload tokens.

**Authentication:** Required (Admin)

**Query Parameters:**
- `skip` (integer, optional): Number of records to skip (default: 0)
- `limit` (integer, optional): Maximum records to return (default: 100)

**Response (200):**
```json
[
  {
    "token": "upload-token-string",
    "download_token": "fbc_download-token-string",
    "expires_at": "2025-12-24T00:00:00Z",
    "uploads_used": 2,
    "max_uploads": 5,
    "max_size_bytes": 104857600,
    "allowed_mime": ["application/pdf"],
    "disabled": false,
    "created_at": "2025-12-23T00:00:00Z",
    "remaining_uploads": 3
  }
]
```

---

### GET /api/tokens/{token_value}

Get detailed information about a specific token.

**Authentication:** Required (Admin, or public if `FBC_ALLOW_PUBLIC_DOWNLOADS=1`)

**Path Parameters:**
- `token_value` (string): Upload token or download token

**Response (200):**
```json
{
  "token": "upload-token-string",
  "download_token": "fbc_download-token-string",
  "expires_at": "2025-12-24T00:00:00Z",
  "uploads_used": 0,
  "max_uploads": 1,
  "max_size_bytes": 104857600,
  "allowed_mime": ["application/pdf"],
  "disabled": false,
  "created_at": "2025-12-23T00:00:00Z",
  "remaining_uploads": 1
}
```

**Error Responses:**
- `404 Not Found` - Token does not exist

---

### PATCH /api/tokens/{token_value}

Update an existing token.

**Authentication:** Required (Admin)

**Path Parameters:**
- `token_value` (string): Upload token or download token

**Request Body:**
```json
{
  "max_uploads": 10,
  "max_size_bytes": 209715200,
  "expiry_datetime": "2025-12-31T23:59:59Z",
  "allowed_mime": ["image/*", "video/*"],
  "disabled": false
}
```

**Fields (all optional):**
- `max_uploads` (integer): Update maximum uploads
- `max_size_bytes` (integer): Update maximum file size
- `expiry_datetime` (datetime): Update expiration date
- `allowed_mime` (array): Update allowed MIME types
- `disabled` (boolean): Enable or disable the token

**Response (200):**
```json
{
  "token": "upload-token-string",
  "download_token": "fbc_download-token-string",
  "expires_at": "2025-12-31T23:59:59Z",
  "uploads_used": 0,
  "max_uploads": 10,
  "max_size_bytes": 209715200,
  "allowed_mime": ["image/*", "video/*"],
  "disabled": false,
  "created_at": "2025-12-23T00:00:00Z",
  "remaining_uploads": 10
}
```

**Error Responses:**
- `404 Not Found` - Token does not exist

---

### DELETE /api/tokens/{token_value}

Delete a token and its associated uploads.

**Authentication:** Required (Admin)

**Path Parameters:**
- `token_value` (string): Upload token or download token

**Query Parameters:**
- `delete_files` (boolean, optional): Whether to delete physical files (default: false)

**Response (204):**
No content

**Error Responses:**
- `404 Not Found` - Token does not exist

**Notes:**
- Deletes the token and all associated upload records
- Physical files are deleted from storage if `delete_files=true`
- This operation cannot be undone

---

### GET /api/tokens/{token_value}/info

Get public token information including uploads.

**Authentication:** None

**Path Parameters:**
- `token_value` (string): The upload token

**Response (200):**
```json
{
  "token": "upload-token-string",
  "download_token": "fbc_download-token-string",
  "remaining_uploads": 1,
  "max_uploads": 1,
  "max_size_bytes": 104857600,
  "max_chunk_bytes": 94371840,
  "allowed_mime": ["application/pdf"],
  "expires_at": "2025-12-24T00:00:00Z",
  "allow_public_downloads": false,
  "uploads": [
    {
      "id": 1,
      "filename": "document.pdf",
      "ext": "pdf",
      "mimetype": "application/pdf",
      "size_bytes": 1024000,
      "meta_data": {"title": "My Document"},
      "upload_length": 1024000,
      "upload_offset": 1024000,
      "status": "completed",
      "created_at": "2025-12-23T12:00:00Z",
      "completed_at": "2025-12-23T12:01:00Z",
      "download_url": "http://localhost:8000/api/tokens/fbc_token/uploads/1",
      "upload_url": "http://localhost:8000/api/uploads/1/tus"
    }
  ]
}
```

**Fields:**
- `remaining_uploads`: Number of uploads still available
- `max_chunk_bytes`: Maximum chunk size for TUS uploads (from `FBC_MAX_CHUNK_BYTES`)
- `allow_public_downloads`: Whether public downloads are enabled
- `uploads`: Array of upload records

**Upload Status Values:**
- `initiated` - Upload created but no data uploaded yet
- `in_progress` - Upload in progress
- `completed` - Upload complete

**Error Responses:**
- `404 Not Found` - Token does not exist

---

### GET /api/tokens/{token_value}/uploads

List all uploads for a specific token.

**Authentication:** Required (Admin, or public if `FBC_ALLOW_PUBLIC_DOWNLOADS=1`)

**Path Parameters:**
- `token_value` (string): Upload token or download token

**Response (200):**
```json
[
  {
    "id": 1,
    "filename": "document.pdf",
    "ext": "pdf",
    "mimetype": "application/pdf",
    "size_bytes": 1024000,
    "meta_data": {"title": "My Document"},
    "upload_length": 1024000,
    "upload_offset": 1024000,
    "status": "completed",
    "created_at": "2025-12-23T12:00:00Z",
    "completed_at": "2025-12-23T12:01:00Z",
    "download_url": "http://localhost:8000/api/tokens/fbc_token/uploads/1",
    "upload_url": "http://localhost:8000/api/uploads/1/tus"
  }
]
```

**Error Responses:**
- `404 Not Found` - Token does not exist

---

### GET /api/tokens/{download_token}/uploads/{upload_id}

Download a completed file.

**Authentication:** Required (Admin, or public if `FBC_ALLOW_PUBLIC_DOWNLOADS=1`)

**Path Parameters:**
- `download_token` (string): The download token (prefixed with `fbc_`)
- `upload_id` (integer): The upload record ID

**Response (200):**
Returns the file with headers:
- `Content-Type`: Original file MIME type or `application/octet-stream`
- `Content-Disposition`: `attachment; filename="original-filename.ext"`
- `Content-Length`: File size in bytes

**Error Responses:**
- `404 Not Found` - Download token or upload not found
- `409 Conflict` - Upload not yet completed

---

### POST /api/uploads/initiate

Initiate a new file upload.

**Authentication:** Required via query parameter

**Query Parameters:**
- `token` (string, required): The upload token

**Request Body:**
```json
{
  "meta_data": {
    "title": "My Document",
    "category": "reports"
  },
  "filename": "document.pdf",
  "filetype": "application/pdf",
  "size_bytes": 1024000
}
```

**Fields:**
- `meta_data` (object, required): Metadata fields validated against `{config_path}/metadata.json` schema
- `filename` (string, optional): Original filename
- `filetype` (string, optional): MIME type
- `size_bytes` (integer, optional): Total file size in bytes (> 0)

**Response (201):**
```json
{
  "upload_id": 1,
  "upload_url": "http://localhost:8000/api/uploads/1/tus",
  "download_url": "http://localhost:8000/api/tokens/fbc_token/uploads/1",
  "meta_data": {
    "title": "My Document",
    "category": "reports"
  },
  "allowed_mime": ["application/pdf"],
  "remaining_uploads": 0
}
```

**Error Responses:**
- `404 Not Found` - Token does not exist
- `403 Forbidden` - Token expired, disabled, or upload limit reached
- `413 Content Too Large` - File size exceeds token limit
- `415 Unsupported Media Type` - File type not allowed for this token
- `422 Unprocessable Entity` - Metadata validation error

---

### OPTIONS /api/uploads/tus

Get TUS protocol capabilities.

**Authentication:** None

**Response (204):**

Headers:
```http
Tus-Resumable: 1.0.0
Tus-Version: 1.0.0
Tus-Extension: creation,termination
```

---

### HEAD /api/uploads/{upload_id}/tus

Check upload status (TUS protocol).

**Authentication:** None

**Path Parameters:**
- `upload_id` (integer): The upload record ID

**Response (200):**

Headers:
```http
Upload-Offset: 512000
Upload-Length: 1024000
Tus-Resumable: 1.0.0
```

**Error Responses:**
- `404 Not Found` - Upload not found
- `409 Conflict` - Upload length unknown

---

### PATCH /api/uploads/{upload_id}/tus

Upload file chunk (TUS protocol).

**Authentication:** None

**Path Parameters:**
- `upload_id` (integer): The upload record ID

**Required Headers:**
- `Upload-Offset` (integer): Current upload offset (must match server state)
- `Tus-Resumable` (string): TUS protocol version (`1.0.0`)
- `Content-Type`: Must be `application/offset+octet-stream`
- `Content-Length` (integer, optional): Chunk size

**Request Body:**
Binary data (file chunk)

**Max Chunk Size:** Controlled by `FBC_MAX_CHUNK_BYTES` (default: 90MB)

**Response (204):**

Headers:
```http
Upload-Offset: 1024000
Tus-Resumable: 1.0.0
Upload-Length: 1024000
```

**Error Responses:**
- `404 Not Found` - Upload not found
- `409 Conflict` - Upload length unknown or mismatched Upload-Offset
- `413 Content Too Large` - Chunk too large or upload exceeds declared length
- `415 Unsupported Media Type` - Invalid Content-Type or actual file mimetype doesn't match allowed types

**Notes:**
- When `upload_offset` equals `upload_length`, the upload is automatically marked as `completed`
- **Server-side MIME type validation**: Upon completion, the server detects the actual file type using libmagic and validates it against the token's `allowed_mime` restrictions. If validation fails, the upload is rejected and deleted (HTTP 415)
- The detected MIME type replaces the client-provided value in the database
- The `uploads_used` counter on the token is incremented upon initiation, not completion

---

### DELETE /api/uploads/{upload_id}/tus

Delete an upload and its associated file (TUS protocol).

**Authentication:** None

**Path Parameters:**
- `upload_id` (integer): The upload record ID

**Response (204):**
No content

**Error Responses:**
- `404 Not Found` - Upload not found

**Notes:**
- Deletes both the database record and the physical file
- This operation cannot be undone

---

### DELETE /api/uploads/{upload_id}/cancel

Cancel an in-progress upload and restore the token slot.

**Authentication:** Required via query parameter

**Path Parameters:**
- `upload_id` (integer): The upload record ID

**Query Parameters:**
- `token` (string, required): The upload token

**Response (200):**
```json
{
  "message": "Upload cancelled successfully",
  "remaining_uploads": 5
}
```

**Error Responses:**
- `404 Not Found` - Upload or token not found
- `409 Conflict` - Upload already completed

**Notes:**
- Restores the upload slot to the token (increments `remaining_uploads`)
- Deletes the physical file if it exists
- Can only cancel uploads that are not completed

---

### POST /api/uploads/{upload_id}/complete

Manually mark an upload as complete.

**Authentication:** None

**Path Parameters:**
- `upload_id` (integer): The upload record ID

**Response (200):**
```json
{
  "id": 1,
  "filename": "document.pdf",
  "ext": "pdf",
  "mimetype": "application/pdf",
  "size_bytes": 1024000,
  "meta_data": {"title": "My Document"},
  "upload_length": 1024000,
  "upload_offset": 1024000,
  "status": "completed",
  "created_at": "2025-12-23T12:00:00Z",
  "completed_at": "2025-12-23T12:01:00Z",
  "download_url": null,
  "upload_url": null
}
```

**Error Responses:**
- `404 Not Found` - Upload not found

---

### GET /api/metadata/

Get the metadata schema configuration.

**Authentication:** None

**Response (200):**
```json
{
  "fields": [
    {
      "key": "title",
      "label": "Title",
      "type": "string",
      "required": true,
      "minLength": 3,
      "maxLength": 100
    },
    {
      "key": "category",
      "label": "Category",
      "type": "select",
      "required": false,
      "options": ["reports", "images", "videos"],
      "allowCustom": false
    }
  ]
}
```

**Field Schema:**

Each field object can have:
- `key` (string, required): Field identifier
- `label` (string, optional): Human-readable label
- `type` (string, required): Field type (`string`, `text`, `number`, `integer`, `boolean`, `date`, `datetime`, `select`, `multiselect`)
- `required` (boolean, optional): Whether field is mandatory
- `options` (array, optional): Available options for select/multiselect
- `allowCustom` (boolean, optional): Allow custom values not in options
- `minLength`, `maxLength` (integer, optional): String length constraints
- `min`, `max` (number, optional): Numeric value constraints
- `regex` (string, optional): Regular expression pattern for string validation
- `default` (any, optional): Default value if not provided

**Notes:**
- Schema is loaded from `{config_path}/metadata.json`

---

### POST /api/metadata/validate

Validate metadata payload against the schema.

**Authentication:** None

**Request Body:**
```json
{
  "metadata": {
    "title": "My Document",
    "category": "reports"
  }
}
```

or direct metadata object:
```json
{
  "title": "My Document",
  "category": "reports"
}
```

**Response (200):**
```json
{
  "metadata": {
    "title": "My Document",
    "category": "reports"
  }
}
```

**Error Responses:**
- `422 Unprocessable Entity` - Validation error
  ```json
  {
    "detail": {
      "field": "title",
      "message": "Must be at least 3 characters"
    }
  }
  ```

**Validation Rules:**
1. **Type Coercion:** Values are automatically converted to the expected type
2. **Required Fields:** Missing required fields result in validation error
3. **String/Text:** Length validated against `minLength`/`maxLength`, pattern validated against `regex`
4. **Number/Integer:** Value validated against `min`/`max`
5. **Boolean:** Accepts various formats (`true`, `1`, `"yes"`, `"on"` → `true`)
6. **Date/DateTime:** Parsed from ISO format string
7. **Select:** Value must be in `options` (unless `allowCustom` is true)
8. **Multiselect:** Each value must be in `options` (unless `allowCustom` is true)

---

### GET /api/notice/

Get the system notice (if configured).

**Authentication:** None

**Response (200):**
```json
{
  "notice": "# Important Notice\n\nThe system will undergo maintenance..."
}
```

**Fields:**
- `notice` (string or null): Markdown content from `{config_path}/notice.md`, or `null` if file doesn't exist

**Notes:**
- Notice is displayed to users in the frontend
- Supports full Markdown formatting

---

### GET /api/admin/validate

Validate the admin API key.

**Authentication:** Required (Admin)

**Response (200):**
```json
{
  "valid": true
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or missing API key

---

### DELETE /api/admin/uploads/{upload_id}

Delete an upload record and its file (Admin only).

**Authentication:** Required (Admin)

**Path Parameters:**
- `upload_id` (integer): The upload record ID

**Response (204):**
No content

**Error Responses:**
- `404 Not Found` - Upload not found

**Notes:**
- Deletes both the database record and the physical file
- Does not restore the upload slot to the token
- This operation cannot be undone

---

## TUS Protocol

The API implements the [TUS resumable upload protocol](https://tus.io/) v1.0.0.

**Supported Extensions:**
- `creation`: Create new uploads
- `termination`: Delete uploads

**Key Features:**
- **Resumable:** Upload can be paused and resumed from the same offset
- **Chunked:** Large files can be split into smaller chunks
- **Verified:** Each chunk is verified by checking the offset

**Required Headers:**
- `Tus-Resumable: 1.0.0` - Protocol version
- `Upload-Offset: <bytes>` - Current upload position
- `Content-Type: application/offset+octet-stream` - Required for PATCH

**Response Headers:**
- `Upload-Offset`: Updated upload position after chunk
- `Upload-Length`: Total file size (if known)
- `Tus-Resumable`: Protocol version echo

---

## Upload Flow

Typical upload flow:

1. **Create Token (Admin)**
   ```http
   POST /api/tokens
   Authorization: Bearer YOUR_API_KEY
   Content-Type: application/json
   
   {
     "max_uploads": 5,
     "max_size_bytes": 104857600,
     "allowed_mime": ["application/pdf"]
   }
   ```

2. **Get Token Info (Client)**
   ```http
   GET /api/tokens/{token}/info
   ```

3. **Initiate Upload (Client)**
   ```http
   POST /api/uploads/initiate?token={token}
   Content-Type: application/json
   
   {
     "meta_data": {"title": "My Document"},
     "filename": "document.pdf",
     "filetype": "application/pdf",
     "size_bytes": 1024000
   }
   ```

4. **Upload File Chunks (TUS Protocol)**
   ```http
   # Check current offset
   HEAD /api/uploads/1/tus
   
   # Upload chunk
   PATCH /api/uploads/1/tus
   Upload-Offset: 0
   Tus-Resumable: 1.0.0
   Content-Type: application/offset+octet-stream
   
   [binary data]
   ```

5. **Download File**
   ```http
   GET /api/tokens/{download_token}/uploads/1
   Authorization: Bearer YOUR_API_KEY
   ```

---

## Error Codes Reference

| Code  | Meaning                | Common Causes                                        |
| ----- | ---------------------- | ---------------------------------------------------- |
| `200` | OK                     | Request successful                                   |
| `201` | Created                | Resource created successfully                        |
| `204` | No Content             | Request successful, no content to return             |
| `400` | Bad Request            | Invalid request format or parameters                 |
| `401` | Unauthorized           | Missing or invalid admin credentials                 |
| `403` | Forbidden              | Token expired, disabled, or limit reached            |
| `404` | Not Found              | Resource not found                                   |
| `409` | Conflict               | Upload not ready, offset mismatch, or state conflict |
| `413` | Content Too Large      | File or chunk exceeds limit                          |
| `415` | Unsupported Media Type | Invalid Content-Type or file type not allowed        |
| `422` | Unprocessable Entity   | Validation error in request body                     |
| `500` | Internal Server Error  | Server-side error                                    |

---

## Notes

- All datetime values are in UTC with ISO 8601 format including timezone info
- File paths are resolved and stored as absolute paths
- Upload tokens are 18-character URL-safe strings
- Download tokens are prefixed with `fbc_` followed by 16-character URL-safe strings
- Metadata is stored as JSON in the database (`meta_data` column)
- TUS protocol is recommended for files larger than a few MB for reliability
- Maximum chunk size is controlled by `FBC_MAX_CHUNK_BYTES` (default: 90MB)
