"""ctypes bridge for the compiled Mojo Huffman kernels."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys

from .huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src", "hpack.mojo")
LIB = os.environ.get("MOJO_HPACK_LIB") or os.path.join(ROOT, "dist", "libmojo-hpack.so")

I = ctypes.c_int64
PARALLEL_MIN_BYTES = 1_048_576
_SIGNATURES = {
    "mh_huffman_encoded_size": ([I, I, I], I),
    "mh_huffman_encode": ([I, I, I, I, I], I),
    "mh_huffman_encode_batch": ([I, I, I, I, I, I, I, I, I], I),
    "mh_huffman_decode": ([I, I, I, I, I, I, I], I),
}


class BuildError(RuntimeError):
    pass


def _mojo_command() -> list[str]:
    override = os.environ.get("MOJO_HPACK_MOJO")
    if override:
        return override.split()
    found = shutil.which("mojo")
    if found:
        return [found]
    pixi = shutil.which("pixi") or os.path.expanduser("~/.pixi/bin/pixi")
    if os.path.exists(pixi):
        return [pixi, "run", "--manifest-path", os.path.join(ROOT, "pixi.toml"), "mojo"]
    raise BuildError("mojo not found; set MOJO_HPACK_MOJO=/path/to/mojo")


def build(force: bool = False) -> str:
    if os.environ.get("MOJO_HPACK_LIB") and os.path.exists(LIB) and not force:
        return LIB
    if not force and os.path.exists(LIB) and os.path.getmtime(LIB) >= os.path.getmtime(SRC):
        return LIB
    os.makedirs(os.path.dirname(LIB), exist_ok=True)
    command = _mojo_command() + ["build", "--emit", "shared-lib", SRC, "-o", LIB]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    if result.returncode or not os.path.exists(LIB):
        raise BuildError((result.stderr or result.stdout).strip()[:4000])
    return LIB


_loaded = None
_parallel_device = None


def lib() -> ctypes.CDLL:
    global _loaded
    if _loaded is None:
        _loaded = ctypes.CDLL(build())
        for name, (argtypes, restype) in _SIGNATURES.items():
            function = getattr(_loaded, name)
            function.argtypes = argtypes
            function.restype = restype
    return _loaded


def _parallel_runtime_ready() -> bool:
    global _parallel_device
    if _parallel_device is None:
        try:
            initialize = lib().KGEN_CompilerRT_AsyncRT_GetOrCreateCPUDevice
            initialize.argtypes = []
            initialize.restype = ctypes.c_void_p
            _parallel_device = initialize() or False
        except (AttributeError, OSError):
            _parallel_device = False
    return bool(_parallel_device)


def _build_trie():
    children = [[-1, -1]]
    symbols = [-1]
    for symbol, (code, width) in enumerate(zip(REQUEST_CODES, REQUEST_CODES_LENGTH)):
        node = 0
        for shift in range(width - 1, -1, -1):
            bit = (code >> shift) & 1
            child = children[node][bit]
            if child < 0:
                child = len(children)
                children[node][bit] = child
                children.append([-1, -1])
                symbols.append(-1)
            node = child
        symbols[node] = symbol
    array_type = ctypes.c_int32 * len(children)
    return (
        array_type(*(entry[0] for entry in children)),
        array_type(*(entry[1] for entry in children)),
        array_type(*symbols),
    )


_CODES = (ctypes.c_uint32 * len(REQUEST_CODES))(*REQUEST_CODES)
_LENGTHS = (ctypes.c_uint8 * len(REQUEST_CODES_LENGTH))(*REQUEST_CODES_LENGTH)
_LEFT, _RIGHT, _SYMBOLS = _build_trie()
_bytes_data = ctypes.pythonapi.PyBytes_AsString
_bytes_data.argtypes = [ctypes.py_object]
_bytes_data.restype = ctypes.c_void_p
_new_bytes = ctypes.pythonapi.PyBytes_FromStringAndSize
_new_bytes.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t]
_new_bytes.restype = ctypes.py_object


def _bytes_address(data: bytes) -> int:
    return _bytes_data(data)


def _allocate_bytes(size: int) -> bytes:
    return _new_bytes(None, size)


def huffman_encode(data: bytes) -> bytes:
    if type(data) is not bytes:
        raise TypeError("data must be bytes")
    if not data:
        return b""
    source_address = _bytes_address(data)
    output_size = lib().mh_huffman_encoded_size(
        source_address, len(data), ctypes.addressof(_LENGTHS)
    )
    if output_size < 0 or output_size > 4 * len(data):
        raise RuntimeError("Mojo Huffman size kernel returned an invalid length")
    destination = _allocate_bytes(output_size)
    destination_address = _bytes_address(destination)
    written = lib().mh_huffman_encode(
        source_address,
        len(data),
        ctypes.addressof(_CODES),
        ctypes.addressof(_LENGTHS),
        destination_address,
    )
    if written != output_size:
        raise RuntimeError("Mojo Huffman encoder returned an invalid length")
    return destination


def huffman_encode_many(values: list[bytes]) -> list[bytes]:
    if type(values) is not list or any(type(value) is not bytes for value in values):
        raise TypeError("values must be a list of bytes")
    count = len(values)
    if not count:
        return []
    source_offsets = (I * (count + 1))()
    position = 0
    for index, value in enumerate(values):
        source_offsets[index] = position
        position += len(value)
    source_offsets[count] = position
    source_data = b"".join(values)
    source_address = _bytes_address(source_data)
    capacity = max(1, (30 * position + 7 * count) // 8)
    destination = _allocate_bytes(capacity)
    destination_address = _bytes_address(destination)
    result_offsets = (I * (count + 1))()
    written = lib().mh_huffman_encode_batch(
        source_address,
        ctypes.addressof(source_offsets),
        count,
        ctypes.addressof(_CODES),
        ctypes.addressof(_LENGTHS),
        destination_address,
        capacity,
        ctypes.addressof(result_offsets),
        _parallel_runtime_ready()
        if count >= 256 and position >= PARALLEL_MIN_BYTES
        else False,
    )
    if written < 0:
        raise RuntimeError("Huffman batch output capacity was insufficient")
    if written > capacity or result_offsets[count] != written:
        raise RuntimeError("Mojo Huffman batch encoder returned invalid offsets")
    previous = 0
    for offset in result_offsets:
        if offset < previous or offset > written:
            raise RuntimeError("Mojo Huffman batch encoder returned invalid offsets")
        previous = offset
    encoded = destination[:written]
    return [
        encoded[result_offsets[index] : result_offsets[index + 1]]
        for index in range(count)
    ]


def huffman_decode(data: bytes) -> bytes:
    if type(data) is not bytes:
        raise TypeError("data must be bytes")
    if not data:
        return b""
    source_address = _bytes_address(data)
    capacity = (len(data) * 8) // 5 + 1
    destination = _allocate_bytes(capacity)
    destination_address = _bytes_address(destination)
    written = lib().mh_huffman_decode(
        source_address,
        len(data),
        ctypes.addressof(_LEFT),
        ctypes.addressof(_RIGHT),
        ctypes.addressof(_SYMBOLS),
        destination_address,
        capacity,
    )
    if written < 0:
        from .exceptions import HPACKDecodingError

        raise HPACKDecodingError("Invalid Huffman string")
    if written > capacity:
        raise RuntimeError("Mojo Huffman decoder returned an invalid length")
    return destination[:written]


def main() -> int:
    print(build(force="--force" in sys.argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
