export interface TusUpload {
  start(): void;
  abort(): Promise<void> | void;
}

export interface UploadMetadata {
  [key: string]: string | number | boolean | Date | string[] | undefined;
}

export type UploadRow = {
  public_id: string;
  title?: string;
  filename?: string;
  ext?: string;
  mimetype?: string;
  source?: string;
  meta_data?: UploadMetadata;
  broadcast_date?: string;
  size_bytes?: number;
  created_at?: string;
  completed_at?: string | null;
  status: string;
  upload_url?: string;
  upload_length?: number;
  upload_offset?: number;
  download_url?: string;
};

export type Slot = {
  file: File | null;
  values: UploadMetadata;
  error: string;
  working: boolean;
  progress: number;
  bytesUploaded?: number;
  status: string;
  errors: string[];
  tusUpload?: TusUpload;
  paused: boolean;
  uploadId?: string;
  initiated: boolean;
};

export interface UploadRowWithSlot extends UploadRow {
  slot?: Slot;
  _reactiveKey?: string;
}

export interface InitiateUploadResponse {
  upload_id: string;
  upload_url: string;
  download_url: string;
  meta_data: UploadMetadata;
  allowed_mime: string[] | null;
  remaining_uploads: number;
}

export interface CancelUploadResponse {
  remaining_uploads: number;
}

export interface ApiError {
  data?: {
    detail?: string;
  };
  message?: string;
  response?: {
    status?: number;
  };
  status?: number;
}
