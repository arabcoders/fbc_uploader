export type UploadRow = {
  id: number;
  title?: string;
  filename?: string;
  ext?: string;
  mimetype?: string;
  source?: string;
  meta_data?: Record<string, any>;
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
  values: Record<string, any>;
  error: string;
  working: boolean;
  progress: number;
  bytesUploaded?: number;
  status: string;
  errors: string[];
  tusUpload?: any;
  paused: boolean;
  uploadId?: number;
  initiated: boolean;
};
