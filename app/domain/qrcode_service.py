import io

import segno
from PIL import Image


def generate_qr_image(content: str) -> bytes:
    try:
        qr = segno.make(content, error="H", version=2)
    except ValueError:
        qr = segno.make(content, error="H")

    buffer_png = io.BytesIO()
    qr.save(buffer_png, kind="png", border=4, scale=20, dark="black", light="white")
    buffer_png.seek(0)

    qr_img = Image.open(buffer_png)

    if qr_img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", qr_img.size, (255, 255, 255))
        if qr_img.mode == "P":
            qr_img = qr_img.convert("RGBA")
        background.paste(qr_img, mask=qr_img.split()[-1] if qr_img.mode == "RGBA" else None)
        qr_img = background
    elif qr_img.mode != "RGB":
        qr_img = qr_img.convert("RGB")

    canvas_width = 1125
    canvas_height = 600
    canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))

    qr_width, qr_height = qr_img.size
    x_offset = (canvas_width - qr_width) // 2
    y_offset = (canvas_height - qr_height) // 2
    canvas.paste(qr_img, (x_offset, y_offset))

    buffer_jpg = io.BytesIO()
    canvas.save(buffer_jpg, format="JPEG", quality=85, optimize=True)
    buffer_jpg.seek(0)
    return buffer_jpg.getvalue()
