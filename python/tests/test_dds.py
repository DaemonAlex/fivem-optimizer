"""DDS container used to hand textures to an external converter and back."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dds


def test_write_then_read_legacy_fourcc_header():
    payload = bytes(range(256)) * 4   # 1024 bytes = 4x4 blocks... any bytes
    blob = dds.write(64, 32, "DXT5", 3, payload)
    assert blob[:4] == b"DDS " and len(blob) == 128 + len(payload)
    w, h, fmt, levels, data = dds.read(blob)
    assert (w, h, fmt, levels) == (64, 32, "DXT5", 3)
    assert data == payload


def test_read_dx10_header_maps_dxgi_to_fourcc_names():
    blob = dds.write(16, 16, "DXT1", 1, b"\0" * 128)
    # rewrite as a DX10 header: fourcc 'DX10' + 20-byte extension with DXGI_FORMAT_BC1_UNORM = 71
    dx10 = bytearray(blob[:128])
    dx10[84:88] = b"DX10"
    ext = struct.pack("<IIIII", 71, 3, 0, 1, 0)
    w, h, fmt, levels, data = dds.read(bytes(dx10) + ext + b"\0" * 128)
    assert (w, h, fmt, levels) == (16, 16, "DXT1", 1)
    assert len(data) == 128


def test_read_rejects_non_dds():
    try:
        dds.read(b"RSC7" + b"\0" * 200)
        assert False
    except ValueError:
        pass
