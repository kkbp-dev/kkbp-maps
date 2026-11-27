"""bundles.py on synthetic UnityFS files: the directory from the header, and data read a block at a time."""

import struct

import pytest

lz4_block = pytest.importorskip("lz4.block")

from kkbp_maps.extractor import bundles  # noqa: E402

BLOCK = 1000


def unityfs(path, files: dict[str, bytes], *, compress=True, at_end=False):
    """A UnityFS bundle holding `files`, its data in blocks of BLOCK bytes, LZ4HC or stored."""
    data = b"".join(files.values())
    chunks = [data[i:i + BLOCK] for i in range(0, len(data), BLOCK)]
    stored = [lz4_block.compress(c, store_size=False) if compress else c for c in chunks]
    info = bytearray(b"\0" * 16) + struct.pack(">i", len(chunks))
    for raw, s in zip(chunks, stored):
        info += struct.pack(">IIH", len(raw), len(s), 3 if compress else 0)
    info += struct.pack(">i", len(files))
    offset = 0
    for name, content in files.items():
        info += struct.pack(">qqI", offset, len(content), 4) + name.encode() + b"\0"
        offset += len(content)
    info_stored = lz4_block.compress(bytes(info), store_size=False)
    head = b"UnityFS\0" + struct.pack(">I", 7) + b"5.x.x\0" + b"2019.4.9f1\0"
    flags = 3 | (bundles.BLOCKS_INFO_AT_END if at_end else 0)
    fixed = len(head) + 20
    pad = (fixed + 15) // 16 * 16 - fixed
    body = b"".join(stored)
    size = fixed + pad + len(body) + len(info_stored)
    header = head + struct.pack(">qIII", size, len(info_stored), len(info), flags) + b"\0" * pad
    path.write_bytes(header + (body + info_stored if at_end else info_stored + body))
    return path


FILES = {"CAB-aaa": bytes(range(256)) * 9, "CAB-aaa.resS": b"pixels" * 700, "CAB-bbb": b"x" * 10}


@pytest.mark.parametrize("compress", [True, False])
@pytest.mark.parametrize("at_end", [False, True])
def test_names_and_data_read_back(tmp_path, compress, at_end):
    path = unityfs(tmp_path / "b.unity3d", FILES, compress=compress, at_end=at_end)
    assert bundles.cab_names(path) == list(FILES)
    blocks = bundles.Blocks(path, cache_blocks=2)
    try:
        for name, offset, size in blocks.nodes:
            assert blocks.read(offset, size) == FILES[name]
            s = blocks.stream(offset, size)
            s.seek(size - 7)
            assert s.read() == FILES[name][-7:]
            s.seek(3)
            assert s.read(5) == FILES[name][3:8]
    finally:
        blocks.close()


def test_the_cab_index_names_each_serialized_file_once(tmp_path):
    (tmp_path / "materials").mkdir()
    unityfs(tmp_path / "materials" / "00.unity3d", FILES)
    unityfs(tmp_path / "materials" / "01.unity3d", {"CAB-ccc": b"y" * 50})
    (tmp_path / "materials" / "broken.unity3d").write_bytes(b"not a bundle")
    index = bundles.cab_index([tmp_path / "materials"])
    assert index == {"cab-aaa": tmp_path / "materials" / "00.unity3d", "cab-bbb": tmp_path / "materials" / "00.unity3d",
                     "cab-ccc": tmp_path / "materials" / "01.unity3d"}


def test_not_a_bundle(tmp_path):
    (tmp_path / "x.unity3d").write_bytes(b"UnityWeb\0")
    with pytest.raises(bundles.NotABundle):
        bundles.cab_names(tmp_path / "x.unity3d")
