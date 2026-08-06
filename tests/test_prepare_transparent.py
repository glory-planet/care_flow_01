from PIL import Image

from dashboard.assets.avatar.prepare_transparent import is_background_pixel, make_transparent


def test_is_background_pixel_true_for_grayscale():
    assert is_background_pixel(50, 50, 50) is True


def test_is_background_pixel_true_for_near_grayscale_under_threshold():
    assert is_background_pixel(50, 55, 48) is True


def test_is_background_pixel_false_for_colorful():
    assert is_background_pixel(195, 199, 122) is False


def test_make_transparent_sets_alpha_correctly(tmp_path):
    # PNG(무손실)로 저장한다 — JPEG는 손실 압축이라 이렇게 작은 테스트 이미지에서는
    # 블록 단위 압축으로 픽셀 값이 크게 왜곡되어 테스트가 알고리즘이 아닌
    # JPEG 압축 아티팩트를 검증하게 되어버린다.
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (50, 50, 50))
    img.putpixel((1, 0), (200, 50, 50))
    input_path = str(tmp_path / "in.png")
    output_path = str(tmp_path / "out.png")
    img.save(input_path)

    make_transparent(input_path, output_path)

    result = Image.open(output_path).convert("RGBA")
    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((1, 0))[3] == 255
