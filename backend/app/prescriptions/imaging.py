"""Upload validation, metadata stripping and image pre-processing. Input is hostile until proven not."""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
import pypdf
import pypdfium2
from PIL import Image, UnidentifiedImageError
from pypdf.errors import PdfReadError

from app.config import get_settings

ALLOWED = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "application/pdf": b"%PDF-",
}
PDF_RENDER_SCALE = 2.0


class UploadRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def sniff_type(data: bytes) -> str:
    """Decide the type from magic bytes. The client's filename and content type are ignored."""
    for mime, magic in ALLOWED.items():
        if data.startswith(magic):
            return mime
    raise UploadRejected("unsupported_type", "Only JPEG, PNG or PDF files are accepted.")


@dataclass
class SanitisedUpload:
    mime: str
    original: bytes
    pages: list[bytes]


def _decode_image(data: bytes) -> Image.Image:
    settings = get_settings()
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > settings.max_image_pixels:
                raise UploadRejected("image_too_large", "The image has too many pixels.")
            if min(width, height) < settings.min_image_side:
                raise UploadRejected("image_too_small", "The image is too small to read.")
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise UploadRejected(
            "corrupt_file", "The file is damaged or is not a valid image."
        ) from exc
    except Image.DecompressionBombError as exc:
        raise UploadRejected("image_too_large", "The image has too many pixels.") from exc
    return image


def strip_image_metadata(image: Image.Image) -> bytes:
    """Re-encode from pixels only, which removes EXIF, GPS and any trailing data."""
    orientation = image.getexif().get(0x0112, 1)
    rotations = {
        3: Image.Transpose.ROTATE_180,
        6: Image.Transpose.ROTATE_270,
        8: Image.Transpose.ROTATE_90,
    }
    clean = image.convert("RGB")
    if orientation in rotations:
        clean = clean.transpose(rotations[orientation])
    pixels_only = Image.new("RGB", clean.size)
    pixels_only.paste(clean)
    output = io.BytesIO()
    pixels_only.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _sanitise_pdf(data: bytes) -> tuple[bytes, list[bytes]]:
    settings = get_settings()
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UploadRejected("encrypted_pdf", "Password-protected PDFs are not accepted.")
        page_count = len(reader.pages)
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        raise UploadRejected("corrupt_file", "The PDF is damaged.") from exc
    if page_count == 0:
        raise UploadRejected("corrupt_file", "The PDF has no pages.")
    if page_count > settings.max_pdf_pages:
        raise UploadRejected(
            "too_many_pages", f"PDFs can have at most {settings.max_pdf_pages} pages."
        )
    # Render pixels only: scripts, attachments, form actions and metadata are left behind.
    pages: list[bytes] = []
    try:
        document = pypdfium2.PdfDocument(data)
        for index in range(page_count):
            bitmap = document[index].render(scale=PDF_RENDER_SCALE)
            image = bitmap.to_pil()
            if image.width * image.height > settings.max_image_pixels:
                raise UploadRejected("image_too_large", "A PDF page is too large.")
            pages.append(strip_image_metadata(image))
        document.close()
    except pypdfium2.PdfiumError as exc:
        raise UploadRejected("corrupt_file", "The PDF could not be rendered.") from exc
    writer = pypdf.PdfWriter()
    writer.append(reader)
    writer.metadata = None
    if "/Metadata" in writer.root_object:
        del writer.root_object["/Metadata"]
    if "/Names" in writer.root_object:
        del writer.root_object["/Names"]  # embedded files and named JavaScript
    if "/OpenAction" in writer.root_object:
        del writer.root_object["/OpenAction"]
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), pages


def sanitise_upload(data: bytes) -> SanitisedUpload:
    settings = get_settings()
    if not data:
        raise UploadRejected("empty_file", "The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise UploadRejected("file_too_large", "The file is larger than the size limit.")
    mime = sniff_type(data)
    if mime == "application/pdf":
        original, pages = _sanitise_pdf(data)
        return SanitisedUpload(mime, original, pages)
    clean = strip_image_metadata(_decode_image(data))
    return SanitisedUpload("image/png", clean, [clean])


def _deskew(gray: np.ndarray) -> np.ndarray:
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    points = cv2.findNonZero(binary)
    if points is None or len(points) < 50:
        return gray
    angle = cv2.minAreaRect(points)[-1]
    if angle > 45:
        angle -= 90
    if abs(angle) < 0.3 or abs(angle) > 15:
        return gray  # large angles are usually layout rather than skew; do not distort the page
    height, width = gray.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _detect_page_region(gray: np.ndarray) -> np.ndarray:
    """Crop to the largest bright region (the paper) when it clearly dominates the photo."""
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return gray
    x, y, width, height = cv2.boundingRect(max(contours, key=cv2.contourArea))
    area_ratio = (width * height) / gray.size
    return gray[y : y + height, x : x + width] if 0.4 < area_ratio < 0.98 else gray


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Orientation, region detection, deskew, denoise and contrast enhancement."""
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if decoded is None:
        raise UploadRejected("corrupt_file", "The image could not be decoded.")
    gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    gray = _detect_page_region(gray)
    gray = _deskew(gray)
    if max(gray.shape) < 1400:
        factor = 1400 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    gray = cv2.fastNlMeansDenoising(gray, None, h=7)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:  # pragma: no cover - encoding a valid array does not fail in practice
        raise UploadRejected("corrupt_file", "The image could not be encoded.")
    return buffer.tobytes()


def scan_for_malware(data: bytes, address: str) -> None:
    """ClamAV INSTREAM hook. When configured, an unreachable scanner rejects the upload."""
    import socket
    import struct

    host, _, port = address.partition(":")
    try:
        with socket.create_connection((host, int(port or 3310)), timeout=30) as connection:
            connection.sendall(b"zINSTREAM\0")
            for start in range(0, len(data), 8192):
                chunk = data[start : start + 8192]
                connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(struct.pack("!I", 0))
            reply = connection.recv(4096).decode(errors="replace")
    except OSError as exc:
        raise UploadRejected(
            "scan_unavailable", "The safety scan is unavailable. Try again later."
        ) from exc
    if "FOUND" in reply:
        raise UploadRejected("malware_detected", "The file failed the safety scan.")
    if "OK" not in reply:
        raise UploadRejected("scan_unavailable", "The safety scan is unavailable. Try again later.")
