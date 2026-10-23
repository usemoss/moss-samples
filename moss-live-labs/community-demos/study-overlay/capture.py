import base64
from io import BytesIO

from mss import mss
from PIL import Image


def capture_screen_png() -> bytes:
    with mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def capture_screen_base64() -> str:
    return base64.b64encode(capture_screen_png()).decode("ascii")


def capture_screen_data_url() -> str:
    return f"data:image/png;base64,{capture_screen_base64()}"
