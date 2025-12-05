import io
from PIL import Image, ExifTags

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_MB = 10


def _strip_exif(img: Image.Image) -> Image.Image:
    data = list(img.getdata())
    img_no_exif = Image.new(img.mode, img.size)
    img_no_exif.putdata(data)
    return img_no_exif


def _auto_orient(img: Image.Image) -> Image.Image:
    try:
        exif = img._getexif()
        if exif is None:
            return img
        orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
        if orientation_key and orientation_key in exif:
            orientation = exif[orientation_key]
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except Exception:
        pass
    return img


def _resize(img: Image.Image, max_px: int) -> Image.Image:
    w, h = img.size
    scale = min(max_px / max(w, h), 1.0)
    if scale < 1.0:
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
    return img


def _to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def validate_and_prepare_image(file_stream, max_px=1920, thumb_px=480) -> dict:
    raw = file_stream.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError("File too large (max 10MB).")

    try:
        img = Image.open(io.BytesIO(raw))
    except Exception:
        raise ValueError("Unsupported or corrupted image file.")

    mime = Image.MIME.get(img.format)
    if mime not in ALLOWED_MIME:
        raise ValueError("Only JPEG, PNG, or WEBP allowed.")

    img = _auto_orient(img)
    img = _strip_exif(img)
    img = img.convert("RGB")

    main = _resize(img, max_px=max_px)
    image_bytes = _to_jpeg_bytes(main, quality=88)

    thumb = _resize(img, max_px=thumb_px)
    thumb_bytes = _to_jpeg_bytes(thumb, quality=80)

    return {
        "image_bytes": image_bytes,
        "thumb_bytes": thumb_bytes
    }
