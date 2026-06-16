"""
Attachment utilities for the Email Communication system.

Supports document attachments only (no images):
- PDF
- CSV
- Excel (xls / xlsx)
- Word (doc / docx)

Uses BLOB storage pattern (same as the surveys app / WHSO activities app).
Max size: 15 MB per file. Oracle-compatible: blobs stored in BinaryField.
"""

import os
import re
import logging

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

MAX_FILE_SIZE_MB = 15
MAX_ATTACHMENTS_PER_EMAIL = 10

# Allowed MIME types (documents only — PDF, CSV, Excel, Word)
ALLOWED_DOCUMENT_MIMES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
    'application/csv',
}

ALLOWED_ATTACHMENT_MIMES = ALLOWED_DOCUMENT_MIMES

# Human-readable format names
MIME_TO_FORMAT = {
    'application/pdf': 'PDF',
    'application/msword': 'Word (DOC)',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word (DOCX)',
    'application/vnd.ms-excel': 'Excel (XLS)',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel (XLSX)',
    'text/csv': 'CSV',
    'application/csv': 'CSV',
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv',
}

# Forbidden extensions (security)
FORBIDDEN_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.com', '.scr', '.vbs', '.js', '.jar',
    '.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.pl', '.sh',
    '.ps1', '.msi', '.dll', '.sys', '.reg', '.hta', '.wsf', '.wsc',
}

# Extension → canonical MIME mapping
EXTENSION_MIME_MAP = {
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.csv': 'text/csv',
}

# MIME → expected extensions (consistency check). CSV is handled separately
# because its magic-byte signature is ambiguous (often detected as text/plain).
MIME_EXTENSION_MAP = {
    'application/pdf': {'.pdf'},
    'application/msword': {'.doc'},
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {'.docx'},
    'application/vnd.ms-excel': {'.xls', '.csv'},  # .csv is often sniffed as ms-excel
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': {'.xlsx'},
}

# MIME types accepted when the file extension is .csv (CSV sniffing is unreliable)
CSV_COMPATIBLE_MIMES = {
    'text/csv',
    'application/csv',
    'text/plain',
    'application/vnd.ms-excel',
    'application/octet-stream',
}

# Windows reserved filenames
RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}

# Dangerous filename characters
DANGEROUS_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# ─── Utilities ───────────────────────────────────────────────────────────────

def sanitize_filename(filename, max_length=255):
    """
    Sanitize filename to prevent path traversal and injection attacks.

    Protections:
    - Path traversal: keeps only the basename
    - Null bytes: stripped
    - Dangerous chars: removed (< > : " / \\ | ? *)
    - Reserved names: prefixed (Windows)
    - Length: truncated while preserving extension
    """
    if not filename:
        raise ValidationError("اسم الملف لا يمكن أن يكون فارغاً")

    filename = os.path.basename(filename)
    filename = filename.replace('\x00', '')
    filename = DANGEROUS_FILENAME_CHARS.sub('', filename)

    if not filename or filename.strip('. ') == '':
        raise ValidationError("اسم الملف يحتوي على أحرف غير صالحة فقط")

    name, ext = os.path.splitext(filename)
    name = name.strip('. ')
    ext = ext.strip('. ')

    if ext:
        ext = f'.{ext}'

    if not name:
        name = "unnamed"

    if name.upper() in RESERVED_NAMES:
        name = f"file_{name}"

    if len(name) + len(ext) > max_length:
        name = name[:max_length - len(ext)]

    return f"{name}{ext}"


def validate_file_type(file):
    """
    Validate file type using magic bytes if available, otherwise by extension.

    Returns:
        str: Canonical MIME type for the file.

    Raises:
        ValidationError: If the file type/extension is not allowed.
    """
    file_ext = os.path.splitext(file.name)[1].lower()

    # Extension gate first (cheap + blocks dangerous types regardless of content)
    if file_ext in FORBIDDEN_EXTENSIONS:
        raise ValidationError(
            f"امتداد الملف '{file_ext}' غير مسموح به لأسباب أمنية."
        )

    if file_ext not in ALLOWED_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(
            f"امتداد الملف '{file_ext}' غير مسموح به. "
            f"الامتدادات المسموحة: {allowed}"
        )

    canonical_mime = EXTENSION_MIME_MAP.get(file_ext, 'application/octet-stream')

    try:
        import magic
        magic_available = True
    except ImportError:
        magic_available = False
        logger.warning("python-magic not installed. Using extension-based validation.")

    if not magic_available:
        # Trust the (already validated) extension
        return canonical_mime

    # Magic-byte detection
    file_start = file.read(2048)
    file.seek(0)

    try:
        detected = magic.from_buffer(file_start, mime=True)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Magic byte detection failed: {e}")
        raise ValidationError("تعذر تحديد نوع الملف. قد يكون الملف تالفاً.")

    detected = (detected or '').lower().strip()

    # CSV: magic sniffing is unreliable (plain text). Trust the extension as long
    # as the detected type is a known text/spreadsheet-compatible type.
    if file_ext == '.csv':
        if detected in CSV_COMPATIBLE_MIMES:
            return 'text/csv'
        raise ValidationError(
            f"محتوى الملف لا يتطابق مع ملف CSV (تم اكتشاف '{detected}'). "
            f"قد يكون الملف مزوراً أو تالفاً."
        )

    # Non-CSV documents: detected MIME must be allowed
    if detected not in ALLOWED_ATTACHMENT_MIMES:
        # Some environments report legacy Office files as application/octet-stream
        if detected == 'application/octet-stream' and file_ext in ('.doc', '.xls'):
            return canonical_mime
        allowed_formats = ', '.join(sorted(set(MIME_TO_FORMAT.values())))
        raise ValidationError(
            f"نوع الملف '{detected}' غير مسموح به. "
            f"الأنواع المسموحة: {allowed_formats}"
        )

    # MIME/extension consistency check
    if detected in MIME_EXTENSION_MAP:
        expected_extensions = MIME_EXTENSION_MAP[detected]
        if file_ext not in expected_extensions:
            raise ValidationError(
                f"امتداد الملف '{file_ext}' لا يتطابق مع نوع الملف المكتشف '{detected}'. "
                f"الامتدادات المتوقعة: {', '.join(sorted(expected_extensions))}. "
                f"قد يكون الملف مزوراً أو تالفاً."
            )

    return detected


def validate_file_size(file, max_size_mb=MAX_FILE_SIZE_MB):
    """
    Validate file size.

    Returns:
        int: File size in bytes.

    Raises:
        ValidationError: If the file exceeds the size limit.
    """
    max_size_bytes = max_size_mb * 1024 * 1024

    if file.size > max_size_bytes:
        raise ValidationError(
            f"حجم الملف ({file.size / 1024 / 1024:.2f} ميغابايت) يتجاوز "
            f"الحد الأقصى المسموح ({max_size_mb} ميغابايت). "
            f"يرجى رفع ملف أصغر."
        )

    return file.size


def validate_attachment_file(file):
    """
    Validate an uploaded attachment file (document only).

    Returns:
        tuple: (mime_type, file_size, sanitized_filename)

    Raises:
        ValidationError: If the file is invalid.
    """
    mime_type = validate_file_type(file)
    file_size = validate_file_size(file)
    sanitized_name = sanitize_filename(file.name)

    format_name = MIME_TO_FORMAT.get(mime_type, mime_type)
    logger.info(
        "Email attachment validated: %s (%s, %.1fKB)",
        sanitized_name, format_name, file_size / 1024,
    )

    return mime_type, file_size, sanitized_name


def process_attachment_upload(uploaded_file):
    """
    Validate and read an uploaded attachment for BLOB storage.

    Returns:
        dict: {
            'file_data': bytes,
            'original_filename': str,
            'file_size': int,
            'mime_type': str,
        }

    Raises:
        ValidationError: If processing fails.
    """
    mime_type, _original_size, sanitized_name = validate_attachment_file(uploaded_file)

    uploaded_file.seek(0)
    file_data = uploaded_file.read()

    return {
        'file_data': file_data,
        'original_filename': sanitized_name,
        'file_size': len(file_data),
        'mime_type': mime_type,
    }


def sync_parent_attachments(parent, fk_name, attachment_ids):
    """
    Reconcile the attachments owned by `parent` (an EmailTemplate or EmailDraft)
    with the provided list of attachment ids.

    Rules:
    - Orphan attachments (no owner) in the list are MOVED to this parent.
    - Attachments owned by a *different* parent (e.g. carried from a template)
      are COPIED so the source is preserved and this parent becomes self-contained.
    - Attachments already owned by this parent are kept.
    - Attachments previously owned by this parent but absent from the list are DELETED.

    Args:
        parent: EmailTemplate or EmailDraft instance (already saved).
        fk_name: 'template' or 'draft'.
        attachment_ids: iterable of attachment UUID strings (or empty).
    """
    from .models import EmailAttachment

    wanted = [str(a) for a in (attachment_ids or [])]
    existing = {
        str(att.id): att
        for att in EmailAttachment.objects.filter(**{fk_name: parent})
    }
    keep_ids = set()

    for aid in wanted:
        if aid in existing:
            keep_ids.add(aid)
            continue

        try:
            src = EmailAttachment.objects.get(id=aid)
        except (EmailAttachment.DoesNotExist, ValueError, ValidationError):
            continue

        is_orphan = (
            src.template_id is None
            and src.draft_id is None
            and src.sent_log_id is None
        )

        if is_orphan:
            setattr(src, fk_name, parent)
            src.save(update_fields=[fk_name])
            keep_ids.add(str(src.id))
        else:
            # Belongs to another owner — copy the blob so we never steal it.
            raw = src.file_data
            file_bytes = raw.read() if hasattr(raw, 'read') else bytes(raw)
            copy = EmailAttachment.objects.create(
                file_data=file_bytes,
                original_filename=src.original_filename,
                file_size=src.file_size,
                mime_type=src.mime_type,
                description=src.description,
                uploaded_by=src.uploaded_by,
                **{fk_name: parent},
            )
            keep_ids.add(str(copy.id))

    # Delete attachments removed from the list
    for aid, att in existing.items():
        if aid not in keep_ids:
            att.delete()
