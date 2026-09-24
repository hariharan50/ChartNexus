"""Turn what was fetched into what should be served.

`fetch-logos.mjs` optimises for *acquisition*: it tries every source and keeps
the widest mark, because keeping the first one that answered shipped half the
board at 16px and the avatars were visibly soft. Those are the right priorities
for finding a logo and the wrong ones for serving it, so delivery is a separate
pass — this one.

Two things are wrong with the raw fetch, and both are fixed here.

**Weight.** The icon services answer at 256px inside a fixed ~270KB envelope,
so an honest fetch lands 17MB in `public/logos/` to draw a 22px square. Resized
to `MAX_PX` and re-encoded, the same marks cost about a tenth of that and no
reader can tell: 128px covers the avatar on a 3x display several times over.

**Format.** The fetcher types a response as SVG-or-PNG from its content type,
and roughly a quarter of what comes back is neither — sites still serve ICO,
and a few serve JPEG. Browsers sniff the bytes so the images do render, but the
file is then served under a `Content-Type` that contradicts its contents, which
is a bug waiting for the first client that believes the header. Decoding and
re-encoding makes the extension true.

    uv run --project ../backend python scripts/normalize-logos.py

Vectors pass through untouched; they are already small and rasterising one
would be a downgrade. Anything that cannot be decoded at all is deleted and
dropped from the manifest, so a symbol falls back to its initials avatar rather
than to a broken image.
"""

from __future__ import annotations

import json
import pathlib

from PIL import Image

HERE = pathlib.Path(__file__).parent
LOGOS = HERE.parent / "public" / "logos"
MANIFEST = HERE.parent / "app" / "lib" / "shared" / "ui" / "logo-manifest.json"

# The avatar draws at 22px and the largest use anywhere is 40px. 128 covers
# that at 3x with room to spare, and is the last power of two where a mark
# still costs less than the request that fetches it.
MAX_PX = 128


def normalize(path: pathlib.Path) -> int | None:
    """Rewrite one raster mark as a true, bounded PNG. None if undecodable."""
    try:
        with Image.open(path) as image:
            # An ICO carries several sizes; Pillow opens the largest only if
            # asked, and the largest is the whole point of this exercise.
            if image.format == "ICO":
                image = image.resize(max(image.ico.sizes()))
            # Paletted and greyscale marks carry transparency a naive convert
            # drops, and a logo that loses its alpha gains a black box.
            image = image.convert("RGBA")
            if max(image.size) > MAX_PX:
                image.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
            image.save(path, format="PNG", optimize=True)
    except Exception:
        return None
    return path.stat().st_size


def main() -> None:
    manifest: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {f"{symbol}.{ext}": symbol for symbol, ext in manifest.items()}

    before = after = 0
    written = pruned = 0
    broken: list[str] = []

    for path in sorted(LOGOS.iterdir()):
        if path.name not in expected:
            path.unlink()
            pruned += 1
            continue

        size = path.stat().st_size
        before += size

        if path.suffix == ".svg":
            after += size
            continue

        result = normalize(path)
        if result is None:
            broken.append(expected[path.name])
            path.unlink()
            continue
        after += result
        written += 1

    for symbol in broken:
        del manifest[symbol]
    if broken:
        MANIFEST.write_text(
            json.dumps(dict(sorted(manifest.items())), indent=2) + "\n", encoding="utf-8"
        )

    print(f"re-encoded {written}, pruned {pruned} stale, dropped {len(broken)} undecodable")
    print(f"{before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
    if broken:
        print("dropped (now fall back to initials):", ", ".join(sorted(broken)))

    # `expected` was taken before the broken entries were removed, so they are
    # subtracted by symbol rather than by filename — the manifest no longer has
    # the extension needed to name their files.
    missing = {
        name
        for name, symbol in expected.items()
        if symbol not in broken and not (LOGOS / name).exists()
    }
    if missing:
        print(f"MANIFEST LISTS {len(missing)} MISSING FILES: {sorted(missing)[:10]}")


if __name__ == "__main__":
    main()
