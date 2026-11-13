import io
import struct
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance

WEB_CLIENT = Path(__file__).resolve().parents[1]
SOURCE = WEB_CLIENT / "assets" / "ved-mark.png"
APP = WEB_CLIENT / "src" / "app"
PUBLIC = WEB_CLIENT / "public"
SPLASH = PUBLIC / "splash"

BACKGROUND = (0, 0, 0)
TILE_NAVY = (11, 16, 32)
CONTENT_THRESHOLD = 16
PALETTE_COLORS = 128
SUPERSAMPLE = 4

MASKABLE_CONTENT_RATIO = 0.8
APPLE_CONTENT_RATIO = 0.92
TILE_CONTENT_RATIO = 0.84
TILE_CORNER_RATIO = 0.22

NORMAL_BRIGHTNESS = 1.0
FAVICON_BRIGHTNESS = 1.35
FAVICON_SIZES = (16, 32, 48)
BRIGHTENED_FAVICON_SIZES = (16, 32)

SPLASH_MARK_RATIO = 0.28
SPLASH_SIZES = (
    (1290, 2796),
    (1179, 2556),
    (1284, 2778),
    (1170, 2532),
    (1125, 2436),
    (1242, 2688),
    (828, 1792),
    (1242, 2208),
    (750, 1334),
    (2048, 2732),
    (1668, 2388),
)

ICO_HEADER = struct.Struct("<HHH")
ICO_ENTRY = struct.Struct("<BBBBHHII")
ICO_ICON_TYPE = 1
ICO_BITS_PER_PIXEL = 32


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


def rounded_tile_mask(size: int) -> Image.Image:
    large = size * SUPERSAMPLE
    mask = Image.new("L", (large, large), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, large - 1, large - 1), radius=large * TILE_CORNER_RATIO, fill=255
    )
    return mask.resize((size, size), Image.BOX)


def build_tile(content: Image.Image, size: int, brightness: float) -> Image.Image:
    inner = round(size * TILE_CONTENT_RATIO)
    scaled = content.resize((inner, inner), Image.LANCZOS)
    mark = ImageEnhance.Brightness(scaled).enhance(brightness)
    offset = (size - inner) // 2
    field = Image.new("RGB", (size, size), BACKGROUND)
    field.paste(mark, (offset, offset))
    navy = Image.new("RGB", (size, size), TILE_NAVY)
    tile = ImageChops.screen(navy, field).convert("RGBA")
    tile.putalpha(rounded_tile_mask(size))
    return tile


def compose_splash(content: Image.Image, width: int, height: int) -> Image.Image:
    side = round(min(width, height) * SPLASH_MARK_RATIO)
    scaled = content.resize((side, side), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    canvas.paste(scaled, ((width - side) // 2, (height - side) // 2))
    return canvas


def quantize(image: Image.Image) -> Image.Image:
    return image.quantize(
        colors=PALETTE_COLORS,
        method=Image.MEDIANCUT,
        dither=Image.FLOYDSTEINBERG,
    )


def encode_png(image: Image.Image) -> bytes:
    if image.mode == "RGBA":
        prepared = quantize(image.convert("RGB")).convert("RGBA")
        prepared.putalpha(image.getchannel("A"))
    else:
        prepared = quantize(image)
    buffer = io.BytesIO()
    prepared.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def write_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_png(image))
    kilobytes = path.stat().st_size // 1024
    width, height = image.size
    print(f"{path.relative_to(WEB_CLIENT)}  {width}x{height}  {kilobytes} KB")


def write_ico(frames: list[Image.Image], path: Path) -> None:
    payloads = [encode_png(frame) for frame in frames]
    offset = ICO_HEADER.size + ICO_ENTRY.size * len(frames)
    directory = bytearray(ICO_HEADER.pack(0, ICO_ICON_TYPE, len(frames)))
    for frame, payload in zip(frames, payloads):
        width, height = frame.size
        directory += ICO_ENTRY.pack(
            width % 256, height % 256, 0, 0, 1, ICO_BITS_PER_PIXEL, len(payload), offset
        )
        offset += len(payload)
    path.write_bytes(bytes(directory) + b"".join(payloads))
    kilobytes = path.stat().st_size // 1024
    sizes = ", ".join(str(frame.size[0]) for frame in frames)
    print(f"{path.relative_to(WEB_CLIENT)}  {sizes}px  {kilobytes} KB")


def corner_alphas(image: Image.Image) -> list[int]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    return [rgba.getpixel(corner)[3] for corner in corners]


def report_corner_alphas(path: Path) -> None:
    with Image.open(path) as opened:
        if path.suffix == ".ico":
            frames = [opened.ico.getimage(size) for size in sorted(opened.ico.sizes())]
        else:
            frames = [opened]
        for frame in frames:
            width = frame.size[0]
            alphas = corner_alphas(frame)
            print(
                f"corner alpha  {path.relative_to(WEB_CLIENT)}  {width}px  "
                f"TL/TR/BL/BR {alphas}"
            )


def write_splashes(content: Image.Image) -> None:
    for width, height in SPLASH_SIZES:
        write_png(compose_splash(content, width, height), SPLASH / f"{width}x{height}.png")


def main() -> None:
    content = trim_to_content(Image.open(SOURCE).convert("RGB"))

    write_png(build_tile(content, 64, NORMAL_BRIGHTNESS), APP / "icon.png")
    write_png(compose(content, 180, APPLE_CONTENT_RATIO), APP / "apple-icon.png")

    write_png(build_tile(content, 192, NORMAL_BRIGHTNESS), PUBLIC / "icon-192.png")
    write_png(build_tile(content, 512, NORMAL_BRIGHTNESS), PUBLIC / "icon-512.png")
    write_png(
        compose(content, 192, MASKABLE_CONTENT_RATIO), PUBLIC / "icon-maskable-192.png"
    )
    write_png(
        compose(content, 512, MASKABLE_CONTENT_RATIO), PUBLIC / "icon-maskable-512.png"
    )
    write_png(
        compose(content, 180, APPLE_CONTENT_RATIO), PUBLIC / "apple-touch-icon.png"
    )

    favicon_frames = [
        build_tile(
            content,
            size,
            FAVICON_BRIGHTNESS if size in BRIGHTENED_FAVICON_SIZES else NORMAL_BRIGHTNESS,
        )
        for size in FAVICON_SIZES
    ]
    write_ico(favicon_frames, APP / "favicon.ico")

    write_splashes(content)

    for path in (
        APP / "icon.png",
        APP / "favicon.ico",
        PUBLIC / "icon-192.png",
        PUBLIC / "icon-512.png",
        PUBLIC / "apple-touch-icon.png",
        APP / "apple-icon.png",
        PUBLIC / "icon-maskable-192.png",
    ):
        report_corner_alphas(path)


if __name__ == "__main__":
    main()
