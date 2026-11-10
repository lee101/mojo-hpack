"""Throwaway A/B harness for the SIMD phase of mojo-hpack.

Times the candidate contiguous loops through the real ctypes bridge so the
rows are comparable to `pixi run bench`. Run under
`flock /tmp/mojo-bench.lock pixi run python bench/.simd-tmp/kernels.py`.
"""

import ctypes
import importlib.util
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "python"))

from hpack._lib import (  # noqa: E402
    _CODES, _LENGTHS, _LEFT, _RIGHT, _SYMBOLS, _allocate_bytes, _bytes_address,
    huffman_decode, huffman_encode, huffman_encode_many, lib,
)

REQUEST_CODES = [ctypes.cast(_CODES, ctypes.POINTER(ctypes.c_uint32))[i] for i in range(257)]
REQUEST_CODES_LENGTH = [_LENGTHS[i] for i in range(257)]

HEADER = (
    b"content-type: application/json; charset=utf-8\r\n"
    b"cache-control: no-cache\r\n"
    b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n"
)
PAYLOAD = HEADER * 512
BATCH = [PAYLOAD[:1024]] * 4096


def best(fn, reps, warm=2):
    for _ in range(warm):
        fn()
    t = float("inf")
    for _ in range(reps):
        s = time.perf_counter()
        fn()
        t = min(t, time.perf_counter() - s)
    return t


def rows():
    m = lib()
    out = []
    data = PAYLOAD
    out.append(("encoded_size 61.4 KB (1 call)",
                best(lambda: m.mh_huffman_encoded_size(_bytes_address(data), len(data), ctypes.addressof(_LENGTHS)), 2000), 2000))
    encoded = huffman_encode(data)
    out.append(("decode 52.5 KB", best(lambda: huffman_decode(encoded), 300), 300))
    out.append(("batch 4.2 MB (4096x1 KB)", best(lambda: huffman_encode_many(BATCH), 5), 5))
    return out


def profile():
    import cProfile
    import pstats
    pr = cProfile.Profile()
    huffman_decode(huffman_encode(PAYLOAD))
    pr.enable()
    for _ in range(50):
        huffman_decode(huffman_encode(PAYLOAD))
    pr.disable()
    pstats.Stats(pr).sort_stats("tottime").print_stats(10)


if __name__ == "__main__":
    if "--profile" in sys.argv:
        profile()
    else:
        print(f"# {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {lib()._name}")
        for name, total, reps in rows():
            print(f"{name:32s} {total / reps * 1e6:10.2f} us  (best of {reps})")
