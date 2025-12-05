import io
from PIL import Image
from services.images import validate_and_prepare_image

def test_resize_and_thumb():
    img = Image.new('RGB', (4000, 1000), color=(123, 222, 111))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)

    out = validate_and_prepare_image(buf, max_px=1920, thumb_px=480)
    assert isinstance(out['image_bytes'], (bytes, bytearray))
    assert isinstance(out['thumb_bytes'], (bytes, bytearray))
