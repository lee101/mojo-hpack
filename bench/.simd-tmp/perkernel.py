"""Per-kernel timing on a quiet CPU, using process CPU time (not wall)."""
import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "python"))

from hpack._lib import _CODES, _LEFT, _LENGTHS, _RIGHT, _SYMBOLS, _bytes_address, lib  # noqa: E402

m = lib()
for name in ("mh_huffman_encoded_size", "mh_huffman_encode", "mh_huffman_decode"):
    fn = getattr(m, name)
    print(name, fn.restype)

HEADER = (
    b"content-type: application/json; charset=utf-8\r\n"
    b"cache-control: no-cache\r\n"
    b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n"
)
PAYLOAD = HEADER * 512


def cpu(fn, reps):
    fn()
    t = time.process_time()
    for _ in range(reps):
        fn()
    return (time.process_time() - t) / reps * 1e6


size = m.mh_huffman_encoded_size(_bytes_address(PAYLOAD), len(PAYLOAD), ctypes.addressof(_LENGTHS))
print("size", size, "us", cpu(lambda: m.mh_huffman_encoded_size(_bytes_address(PAYLOAD), len(PAYLOAD), ctypes.addressof(_LENGTHS)), 200))
dst = b"\0" * size
print("encode us", cpu(lambda: m.mh_huffman_encode(_bytes_address(PAYLOAD), len(PAYLOAD), ctypes.addressof(_CODES), ctypes.addressof(_LENGTHS), _bytes_address(dst)), 200))
dst2 = b"\0" * len(PAYLOAD)
n = m.mh_huffman_decode(_bytes_address(dst), size, ctypes.addressof(_LEFT), ctypes.addressof(_RIGHT), ctypes.addressof(_SYMBOLS), _bytes_address(dst2), len(dst2))
print("decoded", n, "decode us", cpu(lambda: m.mh_huffman_decode(_bytes_address(dst), size, ctypes.addressof(_LEFT), ctypes.addressof(_RIGHT), ctypes.addressof(_SYMBOLS), _bytes_address(dst2), len(dst2)), 200))
print("payload", len(PAYLOAD), "encoded", size)
