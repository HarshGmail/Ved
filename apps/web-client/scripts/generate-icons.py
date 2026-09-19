from pathlib import Path

from PIL import Image, ImageEnhance

WEB_CLIENT = Path(__file__).resolve().parents[1]
SOURCE = WEB_CLIENT / "assets" / "ved-mark.png"
APP = WEB_CLIENT / "src" / "app"
PUBLIC = WEB_CLIENT / "public"

BACKGROUND = (0, 0, 0)
CONTENT_THRESHOLD = 16

MASKABLE_CONTENT_RATIO = 0.8
APPLE_CONTENT_RATIO = 0.92

FAVICON_CROP_RATIO = 0.86
FAVICON_BRIGHTNESS = 1.35
FAVICON_SIZES = [(16, 16), (32, 32), (48, 48)]

PALETTE_COLORS = 128


def trim_to_content(image: Image.Image) -> Image.Image:
    grayscale = image.convert("L")
    bounds = grayscale.point(
        lambda value: 255 if value > CONTENT_THRESHOLD else 0
    ).getbbox()
    left, upper, right, lower = bounds
    size = max(right - left, lower - upper)
    center_x = (left + right) // 2
    center_y = (upper + lower) // 2
    half = size // 2
    return image.crop(
        (center_x - half, center_y - half, center_x + half, center_y + half)
    )


def compose(content: Image.Image, size: int, content_ratio: float) -> Image.Image:
    canvas = Image.new("RGB", (size, size), BACKGROUND)
    inner = int(size * content_ratio)
    scaled = content.resize((inner, inner), Image.LANCZOS)
    offset = (size - inner) // 2
    canvas.paste(scaled, (offset, offset))
    return canvas


def build_favicon_source(content: Image.Image) -> Image.Image:
    size = content.size[0]
    keep = int(size * FAVICON_CROP_RATIO)
    offset = (size - keep) // 2
    cropped = content.crop((offset, offset, offset + keep, offset + keep))
    return ImageEnhance.Brightness(cropped).enhance(FAVICON_BRIGHTNESS)


def quantize(image: Image.Image) -> Image.Image:
    return image.quantize(
        colors=PALETTE_COLORS,
        method=Image.MEDIANCUT,
        dither=Image.FLOYDSTEINBERG,
    )


def write_png(image: Image.Image, path: Path) -> None:
    quantize(image).save(path, "PNG", optimize=True)
    kilobytes = path.stat().st_size // 1024
    print(f"{path.relative_to(WEB_CLIENT)}  {image.size[0]}px  {kilobytes} KB")


def main() -> None:
    content = trim_to_content(Image.open(SOURCE).convert("RGB"))
    full = content.resize((1024, 1024), Image.LANCZOS)

    write_png(full.resize((512, 512), Image.LANCZOS), APP / "icon.png")
    write_png(compose(content, 180, APPLE_CONTENT_RATIO), APP / "apple-icon.png")

    write_png(full.resize((192, 192), Image.LANCZOS), PUBLIC / "icon-192.png")
    write_png(full.resize((512, 512), Image.LANCZOS), PUBLIC / "icon-512.png")
    write_png(
        compose(content, 192, MASKABLE_CONTENT_RATIO), PUBLIC / "icon-maskable-192.png"
    )
    write_png(
        compose(content, 512, MASKABLE_CONTENT_RATIO), PUBLIC / "icon-maskable-512.png"
    )
    write_png(
        compose(content, 180, APPLE_CONTENT_RATIO), PUBLIC / "apple-touch-icon.png"
    )

    favicon_path = APP / "favicon.ico"
    favicon = build_favicon_source(content).resize((48, 48), Image.LANCZOS)
    favicon.convert("RGBA").save(favicon_path, "ICO", sizes=FAVICON_SIZES)
    kilobytes = favicon_path.stat().st_size // 1024
    print(f"src/app/favicon.ico  16-48px  {kilobytes} KB")


if __name__ == "__main__":
    main()
