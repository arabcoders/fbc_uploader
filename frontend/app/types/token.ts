import type { UploadRow } from "./uploads";

export type TokenInfo = {
  token?: string;
  remaining_uploads: number;
  max_uploads: number;
  uploads_used?: number;
  max_size_bytes: number;
  max_chunk_bytes: number;
  allowed_mime?: string[];
  download_token: string;
  expires_at?: string;
  disabled?: boolean;
  allow_public_downloads?: boolean;
  uploads: UploadRow[];
};

export type AdminToken = {
  id: number;
  token: string;
  download_token: string;
  uploads_used: number;
  remaining_uploads: number;
  max_uploads: number;
  max_size_bytes: number;
  allowed_mime?: string[];
  expires_at?: string;
  disabled: boolean;
  created_at: string;
};
