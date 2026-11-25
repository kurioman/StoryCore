"""WebP for Pillow on Android, through the phone's own image decoder.

Chaquopy's Pillow for Android is built without libwebp, but every portrait and picture of the Lore packs is WebP.
This module plugs Android's WebP decoder/encoder (android.graphics.BitmapFactory / Bitmap.compress) into Pillow
as its "WEBP" format, so the shared engine (services/assets.py...) works unchanged: Image.open, verify, size,
convert, crop, resize and save(..., "WEBP") all behave as on PC.

Installed once by mobile_boot.start() before the engine is imported. Does nothing when Pillow already reads WebP.
The Android calls are isolated in the three _android_* functions (replaced by fakes in the tests).
"""
from __future__ import annotations

from PIL import Image, ImageFile, features

FORMAT = "WEBP"


# ----------------------------------------------------------------------------------------------- Android side
def _android_size(data: bytes) -> tuple[int, int]:
    from android.graphics import BitmapFactory
    opts = BitmapFactory.Options()
    opts.inJustDecodeBounds = True
    BitmapFactory.decodeByteArray(data, 0, len(data), opts)
    return int(opts.outWidth), int(opts.outHeight)


def _android_decode(data: bytes) -> tuple[int, int, bytes]:
    """Full decode to straight (non-premultiplied) RGBA bytes."""
    from android.graphics import Bitmap, BitmapFactory
    from java.nio import ByteBuffer
    opts = BitmapFactory.Options()
    opts.inPreferredConfig = Bitmap.Config.ARGB_8888
    opts.inPremultiplied = False
    bmp = BitmapFactory.decodeByteArray(data, 0, len(data), opts)
    if bmp is None:
        raise OSError("Android could not decode this WebP image")
    try:
        w, h = bmp.getWidth(), bmp.getHeight()
        buf = ByteBuffer.allocate(w * h * 4)
        bmp.copyPixelsToBuffer(buf)  # ARGB_8888 is laid out R, G, B, A in memory
        return w, h, bytes(buf.array())
    finally:
        bmp.recycle()


def _android_encode(rgba: bytes, w: int, h: int, quality: int, lossless: bool) -> bytes:
    from android.graphics import Bitmap
    from android.os import Build
    from java.io import ByteArrayOutputStream
    from java.nio import ByteBuffer
    bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
    try:
        bmp.setPremultiplied(False)
        bmp.copyPixelsFromBuffer(ByteBuffer.wrap(rgba))
        if Build.VERSION.SDK_INT >= 30:
            fmt = Bitmap.CompressFormat.WEBP_LOSSLESS if lossless else Bitmap.CompressFormat.WEBP_LOSSY
        else:
            fmt = Bitmap.CompressFormat.WEBP  # Android 7-10: lossy, or lossless at quality 100
            if lossless:
                quality = 100
        out = ByteArrayOutputStream()
        if not bmp.compress(fmt, int(quality), out):
            raise OSError("Android could not encode the WebP image")
        return bytes(out.toByteArray())
    finally:
        bmp.recycle()


# ------------------------------------------------------------------------------------------------ Pillow side
def _accept(prefix: bytes) -> bool:
    return prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP"


class AndroidWebPImageFile(ImageFile.ImageFile):
    format = FORMAT
    format_description = "WebP (Android decoder)"

    def _open(self) -> None:
        self._webp_data = self.fp.read()
        if not _accept(self._webp_data[:16]):
            raise SyntaxError("not a WebP file")
        w, h = _android_size(self._webp_data)
        if w <= 0 or h <= 0:
            raise SyntaxError("WebP image Android cannot read")
        self._size = (w, h)  # only the header: opening (and the engine's scan) stays fast
        self._mode = "RGBA"
        self.tile = []

    def load(self):
        if getattr(self, "_webp_data", None) is not None:
            data, self._webp_data = self._webp_data, None
            w, h, rgba = _android_decode(data)
            decoded = Image.frombuffer("RGBA", (w, h), rgba, "raw", "RGBA", 0, 1)
            decoded.load()
            self.im = decoded.im
            self._size = (w, h)
        return Image.Image.load(self)

    def verify(self) -> None:
        # the header was read by Android in _open; a full decode would only slow the scan down
        if getattr(self, "_webp_data", None) is None and self.im is None:
            raise SyntaxError("WebP image already consumed")


def _save(im: Image.Image, fp, filename) -> None:
    info = im.encoderinfo
    lossless = bool(info.get("lossless", False))
    quality = int(info.get("quality", 80))
    rgba = im.convert("RGBA")
    fp.write(_android_encode(rgba.tobytes(), rgba.width, rgba.height, quality, lossless))


def install() -> bool:
    """Register the Android WebP codec in Pillow. Returns True if it was needed."""
    Image.init()  # load Pillow's own plugins first, so ours replaces its "WEBP" entry and not the reverse
    if features.check("webp"):
        return False
    Image.register_open(FORMAT, AndroidWebPImageFile, _accept)
    Image.register_save(FORMAT, _save)
    Image.register_extensions(FORMAT, [".webp"])
    Image.register_mime(FORMAT, "image/webp")
    return True
