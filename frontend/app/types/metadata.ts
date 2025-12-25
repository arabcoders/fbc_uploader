export type Field = {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  options?: (string | { label: string; value: string })[];
  allowCustom?: boolean;
  placeholder?: string;
  help?: string;
  description?: string;
  min?: number;
  max?: number;
  minLength?: number;
  maxLength?: number;
  default?: any;
  regex?: string;
  extract_regex?: string;
};
