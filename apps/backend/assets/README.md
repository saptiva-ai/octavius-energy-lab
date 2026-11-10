# Assets Directory

This directory contains static assets for document validation.

## Logo Template

**File**: `logo_template.png` (NOT INCLUDED - must be provided)

### Requirements:
- **Format**: PNG (grayscale or color)
- **Recommended size**: 200x100 pixels (or similar aspect ratio)
- **Content**: Demo Capital logo on white or transparent background
- **Quality**: High resolution (will be scaled during matching)

### How to add:
1. Obtain the official Demo Capital logo
2. Convert to PNG format
3. Place in this directory as `logo_template.png`

### Testing without logo:
The logo auditor will gracefully skip validation if the template is missing.
No errors will be thrown, but logo checks won't be performed.

To disable logo validation entirely:
```python
# In API call
POST /api/review/validate?doc_id=xxx&enable_logo=false
```

Or in configuration (`apps/api/config/compliance.yaml`):
```yaml
logo:
  required_pages: []  # Empty list = no logo checks
```
