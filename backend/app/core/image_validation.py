"""Magic-byte validation for user-uploaded images.

The Content-Type header is attacker-controlled — a browser or curl client can
send `Content-Type: image/jpeg` while the body is any payload. We validate
real file signatures so we never store or serve a non-image under an image
MIME type.
"""
from fastapi import HTTPException


_SUPPORTED = {"image/jpeg", "image/png", "image/webp"}


def detect_image_mime(content: bytes) -> str | None:
    """Return the true MIME type of an image based on magic bytes, or None."""
    if len(content) < 12:
        return None
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(content: bytes) -> str:
    """Return the detected MIME, raise 400 if the bytes aren't a supported image.

    Use this instead of trusting ``file.content_type`` on every upload.
    """
    mime = detect_image_mime(content)
    if mime is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid image: file bytes do not match a supported image format",
        )
    if mime not in _SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Image format {mime} not allowed")
    return mime
