"""Bounded, content-addressed PNG backgrounds for the local battle map."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import struct
from tempfile import NamedTemporaryFile
from zlib import crc32, decompressobj, error as ZlibError

from utils.weapon_catalog import application_data_dir


MAX_PNG_BYTES = 16 * 1024 * 1024
MAX_PNG_DIMENSION = 4096
MAX_PNG_PIXELS = 8 * 1024 * 1024
_ID = re.compile(r"[a-f0-9]{64}\Z")
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_BIT_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
          (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


class BattleMapAssetError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MapImage:
    data: bytes
    width: int
    height: int


def _scanline_bytes(width, height, bits, interlace):
    passes = _ADAM7 if interlace else ((0, 0, 1, 1),)
    expected = 0
    for x, y, dx, dy in passes:
        cols, rows = (width - x + dx - 1) // dx, (height - y + dy - 1) // dy
        if cols > 0 and rows > 0:
            expected += rows * (1 + (cols * bits + 7) // 8)
    return expected


def inspect_png(data: bytes) -> MapImage:
    """Check framing and resource bounds before giving the bytes to Tk."""
    if len(data) > MAX_PNG_BYTES:
        raise BattleMapAssetError("battle_map_image_too_large")
    if (len(data) < 45 or not data.startswith(_SIGNATURE)
            or data[8:16] != b"\x00\x00\x00\x0dIHDR"):
        raise BattleMapAssetError("battle_map_image_invalid")
    width, height, depth, color, compression, filter_method, interlace = struct.unpack_from(
        ">IIBBBBB", data, 16,
    )
    if not width or not height or depth not in _BIT_DEPTHS.get(color, ()) or (
        compression or filter_method or interlace not in (0, 1)
    ):
        raise BattleMapAssetError("battle_map_image_invalid")
    if max(width, height) > MAX_PNG_DIMENSION or width * height > MAX_PNG_PIXELS:
        raise BattleMapAssetError("battle_map_image_too_large")

    offset, chunks, idat, palette, idat_finished = 8, 0, False, False, False
    inflater = decompressobj()
    remaining = _scanline_bytes(width, height, depth * _CHANNELS[color], interlace)
    view = memoryview(data)
    while offset + 12 <= len(data) and chunks < 16384:
        size, name = struct.unpack_from(">I4s", data, offset)
        end = offset + 12 + size
        if (end > len(data) or not name.isalpha() or name == b"IHDR" and offset != 8
                or crc32(view[offset + 4:end - 4]) != struct.unpack_from(">I", data, end - 4)[0]):
            break
        if name == b"IEND":
            if idat and inflater.eof and remaining == 0 and not size and end == len(data):
                return MapImage(data, width, height)
            break
        if name == b"PLTE":
            if (idat or palette or color in (0, 4) or size % 3 or not 3 <= size <= 768
                    or color == 3 and size // 3 > 2 ** depth):
                break
            palette = True
        if name == b"IDAT":
            if idat_finished or color == 3 and not palette:
                break
            idat = True
            compressed = view[offset + 8:end - 4]
            try:
                # Stream in modest pieces. Even a valid CRC cannot authorize a
                # decompression larger than the declared, bounded image dimensions.
                while compressed:
                    remaining -= len(inflater.decompress(compressed, min(remaining + 1, 256 * 1024)))
                    if remaining < 0 or inflater.unused_data:
                        raise ZlibError("excess PNG scanline data")
                    compressed = inflater.unconsumed_tail
            except ZlibError:
                break
        elif idat:
            idat_finished = True
        if name[:1].isupper() and name not in (b"IHDR", b"PLTE", b"IDAT"):
            break
        offset = end
        chunks += 1
    raise BattleMapAssetError("battle_map_image_invalid")


def _read_png(path: Path) -> MapImage:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise BattleMapAssetError("battle_map_image_unreadable")
        if info.st_size > MAX_PNG_BYTES:
            raise BattleMapAssetError("battle_map_image_too_large")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                     getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(info, opened):
                raise BattleMapAssetError("battle_map_image_unreadable")
            return inspect_png(stream.read(MAX_PNG_BYTES + 1))
    except OSError as exc:
        raise BattleMapAssetError("battle_map_image_unreadable") from exc


class BattleMapAssetStore:
    """Store only regular validated PNGs under the app's writable data folder."""

    def __init__(self, data_dir=None):
        self.directory = (Path(data_dir) if data_dir is not None else application_data_dir()) / "battle_maps"

    def _path(self, identifier: str) -> Path:
        if not isinstance(identifier, str) or _ID.fullmatch(identifier) is None:
            raise BattleMapAssetError("battle_map_image_invalid_id")
        return self.directory / (identifier + ".png")

    def read_png(self, identifier: str) -> MapImage:
        if self.directory.is_symlink():
            raise BattleMapAssetError("battle_map_image_unreadable")
        image = _read_png(self._path(identifier))
        if sha256(image.data).hexdigest() != identifier:
            raise BattleMapAssetError("battle_map_image_invalid")
        return image

    def import_png(self, path) -> str:
        image = _read_png(Path(path))
        identifier = sha256(image.data).hexdigest()
        dest = self._path(identifier)
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.directory.is_symlink():
                raise BattleMapAssetError("battle_map_image_write_failed")
            if not dest.is_symlink() and not dest.exists():
                with NamedTemporaryFile(dir=self.directory, prefix=".map-", suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(image.data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    if os.name == "nt":
                        os.rename(temporary, dest)  # Windows rename cannot overwrite.
                    else:
                        os.link(temporary, dest)  # POSIX rename would overwrite a race winner.
                except FileExistsError:
                    pass
            self.read_png(identifier)
        except OSError as exc:
            raise BattleMapAssetError("battle_map_image_write_failed") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # A cleanup failure cannot invalidate an already saved map.
        return identifier
