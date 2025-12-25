# Dynamic Upload Metadata Schema

Upload metadata fields are defined in `{config_path}/metadata.json`. This file contains a list of field definitions that describe how metadata is collected, validated, and stored for each upload.

---

## Field Definition

Each field supports the following properties.

### Required Properties

* **`key`** *(string, unique)*
  Unique identifier used in API payloads and stored metadata.
* **`label`** *(string)*
  Human-readable label displayed in the UI.
* **`type`** *(string)*
  Data type of the field. Supported values:
  `string`, `text`, `number`, `integer`, `boolean`, `date`, `datetime`, `select`, `multiselect`.

---

### Common Properties

* **`required`** *(boolean)*
  Whether the field must be present and non-empty.
* **`placeholder`** *(string)*
  Placeholder text shown in the UI.
* **`help` / `description`** *(string)*
  Helper text displayed below the input.
* **`default`** *(any)*
  Default value applied when the field is not explicitly set.

---

### Select and Multiselect Properties

* **`options`** *(array)*
  Allowed values. Each entry may be a string or an object of the form
  `{ "label": "...", "value": "..." }`.
* **`allowCustom`** *(boolean)*
  When enabled, users may provide values not listed in `options` (the UI uses a datalist-style input).

---

### Validation Rules

* **`min`, `max`**
  Numeric bounds for `number` and `integer` fields.
* **`minLength`, `maxLength`**
  Length constraints for `string` and `text` fields.
* **`regex`**
  Regular expression the value must match. Enforced both on the frontend and backend.

---

### Frontend Extraction (Optional)

* **`extract_regex`**
  Optional regular expression applied to the uploaded filename to prefill the field.
  If the pattern matches, capture group 1 is used; otherwise, the full match is used.

---

## Behavior

* The active schema is exposed via **`GET /api/metadata`**.
* During upload initiation, metadata is validated server-side against the schema.
* The frontend mirrors the same validation rules and applies `extract_regex` for prefilling fields.
* Metadata is stored per upload as JSON in the `meta_data` field.
