"""UnityFS bundles read without UnityPy: their files' names, and their data a block at a time.

UnityPy decompresses a whole bundle into memory before it reads anything from it, which for KKS's shared
`map/materials/00` (815 MB, 1.7 GB decompressed) costs 3.6 GB per Map (kks-spike.md, section 6). A Map
needs a small part of it. So `Blocks` decompresses a block only when a read reaches it, and keeps a
few, and `unity.py` hands UnityPy a stream over each file of the bundle instead of the bundle.

`cab_names` reads only a bundle's header and directory, which name the serialized files (CABs) inside
it, so the bundle a Map's external reference points into can be found without opening any bundle.
Standard library and lz4 only (lz4 is one of UnityPy's own dependencies, ADR 0029).
"""

from __future__ import annotations

import io
import struct
from bisect import bisect_right
from collections import OrderedDict
from pathlib import Path

NONE, LZMA, LZ4, LZ4HC = 0, 1, 2, 3
BLOCKS_INFO_AT_END = 0x80
BLOCK_INFO_PADDING = 0x200
SUFFIX = ".unity3d"


class NotABundle(ValueError):
    pass


def _cstr(f) -> str:
    b = bytearray()
    while (c := f.read(1)) not in (b"", b"\0"):
        b += c
    return b.decode("utf-8")


def _decompress(data: bytes, size: int, kind: int) -> bytes:
    if kind == NONE:
        return data
    if kind in (LZ4, LZ4HC):
        import lz4.block
        return lz4.block.decompress(data, uncompressed_size=size)
    raise NotImplementedError(f"bundle compression {kind} isn't read")   # LZMA: none of the Games uses it


def _directory(f, path: Path):
    """(blocks as (file offset, compressed size, size, kind), nodes as (name, offset, size)) of an open
    UnityFS file, from its header and its blocks-info section only."""
    if _cstr(f) != "UnityFS":
        raise NotABundle(f"{path} isn't a UnityFS bundle")
    version = struct.unpack(">I", f.read(4))[0]
    _cstr(f), _cstr(f)
    size, csize, usize, flags = struct.unpack(">qIII", f.read(20))
    if version >= 7:
        f.seek((f.tell() + 15) // 16 * 16)
    data_start = f.tell()
    if flags & BLOCKS_INFO_AT_END:
        f.seek(size - csize)
    info = _decompress(f.read(csize), usize, flags & 0x3F)
    if not flags & BLOCKS_INFO_AT_END:
        data_start = f.tell()
    if flags & BLOCK_INFO_PADDING:
        data_start = (data_start + 15) // 16 * 16
    p = 16   # the uncompressed data's hash
    (count,) = struct.unpack(">i", info[p:p + 4])
    p += 4
    blocks, offset = [], data_start
    for _ in range(count):
        u, c, fl = struct.unpack(">IIH", info[p:p + 10])
        p += 10
        blocks.append((offset, c, u, fl & 0x3F))
        offset += c
    (count,) = struct.unpack(">i", info[p:p + 4])
    p += 4
    nodes = []
    for _ in range(count):
        off, sz, _fl = struct.unpack(">qqI", info[p:p + 20])
        p += 20
        end = info.index(b"\0", p)
        nodes.append((info[p:end].decode("utf-8"), off, sz))
        p = end + 1
    return blocks, nodes


def cab_names(path: Path) -> list[str]:
    """The names of the files inside a bundle, from its header alone."""
    with open(path, "rb") as f:
        return [name for name, _, _ in _directory(f, Path(path))[1]]


def cab_index(folders) -> dict[str, Path]:
    """Every serialized file (CAB) in the bundles under `folders`, lower-cased, to its bundle. A name in
    two bundles keeps the first in path order."""
    index: dict[str, Path] = {}
    for folder in folders:
        for bundle in sorted(Path(folder).rglob(f"*{SUFFIX}")):
            try:
                names = cab_names(bundle)
            except (NotABundle, OSError, struct.error, ValueError, NotImplementedError):
                continue
            for name in names:
                if not name.lower().endswith((".ress", ".resource")):
                    index.setdefault(name.lower(), bundle)
    return index


class Blocks:
    """The data of a UnityFS bundle, decompressed a block at a time when a read reaches it."""

    def __init__(self, path: Path, cache_blocks: int = 64):
        self.path = Path(path)
        self.file = open(self.path, "rb")
        try:
            self.blocks, self.nodes = _directory(self.file, self.path)
        except Exception:
            self.file.close()
            raise
        self.starts, total = [], 0
        for _, _, u, _ in self.blocks:
            self.starts.append(total)
            total += u
        self.size = total
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self._cache_blocks = cache_blocks

    def close(self):
        self._cache.clear()
        self.file.close()

    def _block(self, i: int) -> bytes:
        b = self._cache.get(i)
        if b is not None:
            self._cache.move_to_end(i)
            return b
        offset, c, u, kind = self.blocks[i]
        self.file.seek(offset)
        b = _decompress(self.file.read(c), u, kind)
        self._cache[i] = b
        if len(self._cache) > self._cache_blocks:
            self._cache.popitem(last=False)
        return b

    def read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        while size > 0 and offset < self.size:
            i = bisect_right(self.starts, offset) - 1
            start, c, u, kind = self.blocks[i]
            inner = offset - self.starts[i]
            n = min(size, u - inner)
            if kind == NONE:   # stored as is: read straight from the file, nothing cached
                self.file.seek(start + inner)
                out += self.file.read(n)
            else:
                out += self._block(i)[inner:inner + n]
            offset += n
            size -= n
        return bytes(out)

    def stream(self, offset: int, size: int) -> io.BufferedReader:
        """One file of the bundle as a seekable binary stream."""
        return io.BufferedReader(_NodeStream(self, offset, size), buffer_size=1 << 16)


class _NodeStream(io.RawIOBase):
    def __init__(self, blocks: Blocks, offset: int, size: int):
        self.blocks, self.offset, self.size, self.pos = blocks, offset, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, pos, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(0, base + pos)
        return self.pos

    def readinto(self, b):
        n = max(0, min(len(b), self.size - self.pos))
        data = self.blocks.read(self.offset + self.pos, n)
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)
