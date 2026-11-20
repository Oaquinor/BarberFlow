"""Image decoding and normalization checks independent of the MySQL integration DB."""

from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.v1.endpoints import onboarding


def _image_bytes(image_format: str = "PNG") -> bytes:
    output = BytesIO()
    mode = "RGBA" if image_format == "PNG" else "RGB"
    color = (40, 90, 160, 180) if image_format == "PNG" else (40, 90, 160)
    Image.new(mode, (2, 2), color).save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize(("mime_type", "image_format"), [
    ("image/png", "PNG"),
    ("image/jpeg", "JPEG"),
])
def test_logo_sanitization_keeps_only_the_valid_expected_raster(mime_type, image_format):
    sanitized = onboarding._sanitize_logo(
        _image_bytes(image_format), onboarding.LOGO_IMAGE_FORMATS[mime_type],
    )

    with Image.open(BytesIO(sanitized)) as image:
        assert image.format == image_format
        assert image.size == (2, 2)
        assert getattr(image, "n_frames", 1) == 1
        if image_format == "PNG":
            assert image.mode == "RGBA"
            assert image.getpixel((0, 0))[3] == 180
        else:
            assert image.mode == "RGB"


def test_logo_sanitization_rejects_corrupt_and_mismatched_image_bytes():
    with pytest.raises(HTTPException) as corrupt:
        onboarding._sanitize_logo(b"\x89PNG\r\n\x1a\nnot an image", "PNG")
    assert corrupt.value.status_code == 400

    with pytest.raises(HTTPException) as mismatch:
        onboarding._sanitize_logo(_image_bytes("PNG"), "JPEG")
    assert mismatch.value.status_code == 400


def test_logo_sanitization_rejects_oversized_dimensions(monkeypatch):
    monkeypatch.setattr(onboarding, "MAX_LOGO_PIXELS", 3)

    with pytest.raises(HTTPException) as oversized:
        onboarding._sanitize_logo(_image_bytes(), "PNG")
    assert oversized.value.status_code == 400


def test_logo_sanitization_rejects_animated_png():
    output = BytesIO()
    first = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    second = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    first.save(output, format="PNG", save_all=True, append_images=[second], duration=100)

    with pytest.raises(HTTPException) as animated:
        onboarding._sanitize_logo(output.getvalue(), "PNG")
    assert animated.value.status_code == 400
