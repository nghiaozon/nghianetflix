from pathlib import Path
import sys

from PIL import Image, ImageDraw


SOURCE = Path(sys.argv[1])
OUTPUT = Path(__file__).resolve().parents[1] / "assets"
SIZES = (16, 32, 48, 64, 128, 256)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as source:
        image = source.convert("RGB")
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        square = image.crop((left, top, left + side, top + side))
        master = square.resize((1024, 1024), Image.Resampling.LANCZOS)
        master.save(OUTPUT / "app-logo-square.png", optimize=True)

        circle = master.convert("RGBA")
        mask = Image.new("L", circle.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 1023, 1023), fill=255)
        circle.putalpha(mask)
        circle.save(OUTPUT / "app-logo-circle.png", optimize=True)

        frames = [circle.resize((size, size), Image.Resampling.LANCZOS) for size in SIZES]
        frames[-1].save(
            OUTPUT / "app.ico", format="ICO", append_images=frames[:-1],
            sizes=[(size, size) for size in SIZES],
        )


if __name__ == "__main__":
    main()
