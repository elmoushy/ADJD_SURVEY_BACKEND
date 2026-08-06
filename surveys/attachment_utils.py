"""
Attachment utilities for survey responses, follow-up messages and surveys.

Supports:
- Documents: PDF, Word (doc/docx), Excel (xls/xlsx)
- Presentations: PowerPoint (ppt/pptx) — survey attachments only
- Images: JPEG, PNG, GIF (stored as-is, no optimization)

Uses BLOB storage pattern (same as WHSO_Weapon_Backend activities app).
No thumbnails — files are served as downloads only.
"""

import io
import os
import re
import logging
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

MAX_FILE_SIZE_MB = 10
MAX_ATTACHMENTS_PER_SUBMISSION = 5

# Max attachments a creator can pin to a single survey (reference material
# respondents read while answering).
MAX_ATTACHMENTS_PER_SURVEY = 5

# Allowed MIME types
ALLOWED_DOCUMENT_MIMES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

ALLOWED_PRESENTATION_MIMES = {
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

ALLOWED_IMAGE_MIMES = {
    'image/jpeg',
    'image/png',
    'image/gif',
}

ALLOWED_ATTACHMENT_MIMES = ALLOWED_DOCUMENT_MIMES | ALLOWED_IMAGE_MIMES

# Survey attachments additionally accept PowerPoint decks. Kept as a separate
# set so widening it never changes what respondents may upload.
ALLOWED_SURVEY_ATTACHMENT_MIMES = ALLOWED_ATTACHMENT_MIMES | ALLOWED_PRESENTATION_MIMES

# Human-readable format names
MIME_TO_FORMAT = {
    'application/pdf': 'PDF',
    'application/msword': 'Word (DOC)',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word (DOCX)',
    'application/vnd.ms-excel': 'Excel (XLS)',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel (XLSX)',
    'application/vnd.ms-powerpoint': 'PowerPoint (PPT)',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PowerPoint (PPTX)',
    'image/jpeg': 'Image (JPEG)',
    'image/png': 'Image (PNG)',
    'image/gif': 'Image (GIF)',
}

# MIME types browsers can render in a tab (opened inline instead of downloaded)
INLINE_VIEWABLE_MIMES = ALLOWED_IMAGE_MIMES | {'application/pdf'}

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.jpg', '.jpeg', '.png', '.gif',
}

ALLOWED_PRESENTATION_EXTENSIONS = {'.ppt', '.pptx'}

ALLOWED_SURVEY_EXTENSIONS = ALLOWED_EXTENSIONS | ALLOWED_PRESENTATION_EXTENSIONS

# Forbidden extensions (security)
FORBIDDEN_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.com', '.scr', '.vbs', '.js', '.jar',
    '.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.pl', '.sh',
    '.ps1', '.msi', '.dll', '.sys', '.reg', '.hta', '.wsf', '.wsc',
}

# MIME to extension mapping for consistency checks
MIME_EXTENSION_MAP = {
    'application/pdf': {'.pdf'},
    'application/msword': {'.doc'},
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {'.docx'},
    'application/vnd.ms-excel': {'.xls'},
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': {'.xlsx'},
    'application/vnd.ms-powerpoint': {'.ppt'},
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': {'.pptx'},
    'image/jpeg': {'.jpg', '.jpeg'},
    'image/png': {'.png'},
    'image/gif': {'.gif'},
}

# Extension → MIME map used when magic-byte detection is unavailable
EXTENSION_MIME_MAP = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
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

# Generic types libmagic reports for Office containers: OOXML files (docx/xlsx/
# pptx) are ZIP archives and legacy Office files are OLE2 compound documents,
# so detection alone cannot tell them apart from a plain archive.
CONTAINER_MIMES = {
    'application/zip',
    'application/x-zip-compressed',
    'application/octet-stream',
    'application/CDFV2',
    'application/x-ole-storage',
}

# Office extensions whose real type may only be recoverable from the extension
OFFICE_CONTAINER_EXTENSIONS = {
    '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt',
}


def is_image_mime(mime_type):
    """Check if MIME type is an image."""
    return mime_type in ALLOWED_IMAGE_MIMES


def is_document_mime(mime_type):
    """Check if MIME type is a document."""
    return mime_type in ALLOWED_DOCUMENT_MIMES


def is_presentation_mime(mime_type):
    """Check if MIME type is a presentation (PowerPoint)."""
    return mime_type in ALLOWED_PRESENTATION_MIMES


def is_inline_viewable_mime(mime_type):
    """Check if browsers can render this type in a tab instead of downloading it."""
    return mime_type in INLINE_VIEWABLE_MIMES


def sanitize_filename(filename, max_length=255):
    """
    Sanitize filename to prevent path traversal and injection attacks.
    
    Protections:
    - Path traversal: Removes ../../ patterns
    - Null bytes: Strips \\x00 characters
    - Dangerous chars: Removes <, >, :, ", /, \\, |, ?, *
    - Reserved names: Prefixes Windows reserved names
    - Length limits: Truncates while preserving extension
    """
    if not filename:
        raise ValidationError("اسم الملف لا يمكن أن يكون فارغاً")

    # Remove path components
    filename = os.path.basename(filename)

    # Remove null bytes
    filename = filename.replace('\x00', '')

    # Remove dangerous characters
    filename = DANGEROUS_FILENAME_CHARS.sub('', filename)

    if not filename or filename.strip('. ') == '':
        raise ValidationError("اسم الملف يحتوي على أحرف غير صالحة فقط")

    # Split name and extension
    name, ext = os.path.splitext(filename)
    name = name.strip('. ')
    ext = ext.strip('. ')

    if ext:
        ext = f'.{ext}'

    if not name:
        name = "unnamed"

    # Check reserved names
    if name.upper() in RESERVED_NAMES:
        name = f"file_{name}"

    # Truncate if too long
    if len(name) + len(ext) > max_length:
        name = name[:max_length - len(ext)]

    return f"{name}{ext}"


def _allowed_formats_text(allowed_mimes):
    """Human-readable list of the allowed formats, for error messages."""
    names = {MIME_TO_FORMAT.get(m, m) for m in allowed_mimes}
    return ', '.join(sorted(names))


def _validate_extension(file_ext, allowed_extensions):
    """Reject forbidden/unknown extensions. Shared by both detection paths."""
    if file_ext in FORBIDDEN_EXTENSIONS:
        raise ValidationError(
            f"امتداد الملف '{file_ext}' غير مسموح به لأسباب أمنية."
        )

    if file_ext not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise ValidationError(
            f"امتداد الملف '{file_ext}' غير مسموح به. "
            f"الامتدادات المسموحة: {allowed}"
        )


def validate_file_type(file, allowed_mimes=None, allowed_extensions=None):
    """
    Validate file type using magic bytes if available, otherwise by extension.

    Args:
        file: Django UploadedFile object
        allowed_mimes: Permitted MIME types (defaults to response/follow-up set)
        allowed_extensions: Permitted extensions (defaults to response/follow-up set)

    Returns:
        str: Detected MIME type

    Raises:
        ValidationError: If file type is not allowed
    """
    allowed_mimes = allowed_mimes or ALLOWED_ATTACHMENT_MIMES
    allowed_extensions = allowed_extensions or ALLOWED_EXTENSIONS

    try:
        import magic
        magic_available = True
    except ImportError:
        magic_available = False
        logger.warning("python-magic not installed. Using extension-based validation.")

    file_ext = os.path.splitext(file.name)[1].lower()

    if not magic_available:
        # Fallback: extension-based validation
        _validate_extension(file_ext, allowed_extensions)
        return EXTENSION_MIME_MAP.get(file_ext, 'application/octet-stream')

    # Use magic bytes detection
    file_start = file.read(2048)
    file.seek(0)

    try:
        mime = magic.from_buffer(file_start, mime=True)
    except Exception as e:
        logger.error(f"Magic byte detection failed: {e}")
        raise ValidationError("تعذر تحديد نوع الملف. قد يكون الملف تالفاً.")

    mime = mime.lower().strip()

    # Extension is checked before the MIME verdict so a forbidden extension is
    # always rejected, whatever the detected type says.
    _validate_extension(file_ext, allowed_extensions)

    # Office files are containers (OOXML = ZIP, legacy Office = OLE2), so
    # libmagic reports a generic container type for them. In that case fall back
    # to the extension-derived type — the extension is already whitelisted above.
    if mime in CONTAINER_MIMES and file_ext in OFFICE_CONTAINER_EXTENSIONS:
        resolved = EXTENSION_MIME_MAP.get(file_ext)
        if resolved:
            logger.info(
                "Office container detected as '%s'; resolved to '%s' from extension '%s'",
                mime, resolved, file_ext,
            )
            mime = resolved

    if mime not in allowed_mimes:
        raise ValidationError(
            f"نوع الملف '{mime}' غير مسموح به. "
            f"الأنواع المسموحة: {_allowed_formats_text(allowed_mimes)}"
        )

    # MIME/extension consistency check
    if mime in MIME_EXTENSION_MAP:
        expected_extensions = MIME_EXTENSION_MAP[mime]
        if file_ext not in expected_extensions:
            raise ValidationError(
                f"امتداد الملف '{file_ext}' لا يتطابق مع نوع الملف المكتشف '{mime}'. "
                f"الامتدادات المتوقعة: {', '.join(sorted(expected_extensions))}. "
                f"قد يكون الملف مزوراً أو تالفاً."
            )

    return mime


def validate_file_size(file, max_size_mb=MAX_FILE_SIZE_MB):
    """
    Validate file size.
    
    Returns:
        int: File size in bytes
        
    Raises:
        ValidationError: If file exceeds size limit
    """
    max_size_bytes = max_size_mb * 1024 * 1024

    if file.size > max_size_bytes:
        raise ValidationError(
            f"حجم الملف ({file.size / 1024 / 1024:.2f} ميغابايت) يتجاوز "
            f"الحد الأقصى المسموح ({max_size_mb} ميغابايت). "
            f"يرجى رفع ملف أصغر."
        )

    return file.size


def validate_attachment_file(file, allowed_mimes=None, allowed_extensions=None):
    """
    Validate uploaded attachment file (document, presentation or image).

    Args:
        file: Django UploadedFile object
        allowed_mimes: Permitted MIME types (defaults to response/follow-up set)
        allowed_extensions: Permitted extensions (defaults to response/follow-up set)

    Returns:
        tuple: (mime_type, file_size, sanitized_filename)

    Raises:
        ValidationError: If file is invalid
    """
    # Validate file type (magic bytes or extension)
    mime_type = validate_file_type(file, allowed_mimes, allowed_extensions)

    # Validate file size
    file_size = validate_file_size(file)

    # Sanitize filename
    sanitized_name = sanitize_filename(file.name)

    format_name = MIME_TO_FORMAT.get(mime_type, mime_type)
    logger.info(f"Attachment validated: {sanitized_name} ({format_name}, {file_size / 1024:.1f}KB)")

    return mime_type, file_size, sanitized_name


def process_attachment_upload(uploaded_file, allowed_mimes=None, allowed_extensions=None):
    """
    Process and validate attachment for BLOB storage.

    Files (both documents and images) are stored as-is.
    No image optimization or thumbnail generation.

    Args:
        uploaded_file: Django UploadedFile object
        allowed_mimes: Permitted MIME types (defaults to response/follow-up set)
        allowed_extensions: Permitted extensions (defaults to response/follow-up set)

    Returns:
        dict: {
            'file_data': bytes,
            'original_filename': str,
            'file_size': int,
            'mime_type': str,
        }
        
    Raises:
        ValidationError: If processing fails
    """
    mime_type, original_size, sanitized_name = validate_attachment_file(
        uploaded_file, allowed_mimes, allowed_extensions
    )

    # Reset file pointer after validation
    uploaded_file.seek(0)

    # Read file data
    file_data = uploaded_file.read()

    return {
        'file_data': file_data,
        'original_filename': sanitized_name,
        'file_size': len(file_data),
        'mime_type': mime_type,
    }
