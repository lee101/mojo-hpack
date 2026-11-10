"""Correctness check: candidate vs base .so vs the Python bridge.

All inputs live in persistent ctypes buffers so the raw pointers stay valid.
"""
import ctypes
import random
import sys

sys.path.insert(0, "bench/.simd-tmp")
from compare import PAYLOAD, Lib, load  # noqa: E402

L = load()
base = Lib("bench/.simd-tmp/base.so")
import os
cand = Lib("bench/.simd-tmp/cand.so")
_CODES = L._CODES
_LENGTHS = L._LENGTHS
codes = ctypes.addressof(_CODES)
lengths = ctypes.addressof(_LENGTHS)
SYMBOLS = {
    "base": ("mh_huffman_encoded_size", "mh_huffman_encode"),
    "cand": ("c1_size", "c1_encode"),
}


def encode_with(which, data):
    size_name, encode_name = SYMBOLS[which]
    lib = {"base": base, "cand": cand}[which]
    n = len(data)
    src = ctypes.create_string_buffer(data, n)
    size = lib.f(size_name)(ctypes.addressof(src), n, lengths)
    dst = ctypes.create_string_buffer(size + 16)
    written = lib.f(encode_name)(ctypes.addressof(src), n, codes, lengths, ctypes.addressof(dst))
    return size, written, dst.raw[:written], (src, dst)


def main():
    rng = random.Random(5)
    ok = True
    keep = []
    for n in (1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 1000, 65_537):
        data = rng.randbytes(n)
        ref = L.huffman_encode(data)
        sb, rb, ob, kb = encode_with("base", data)
        sc, rc, oc, kc = encode_with("cand", data)
        keep += [kb, kc]
        good = sb == sc == len(ref) and rb == rc and ob == oc == ref
        ok &= good
        print(f"n={n:6d} ok={good} size={sb}/{sc} ret={rb}/{rc} len={len(ref)}", flush=True)
    for n in (1, 7, 8, 9, 100, 1001, 6048, 61440):
        data = (PAYLOAD * 2)[:n]
        ref = L.huffman_encode(data)
        sc, rc, oc, kc = encode_with("cand", data)
        keep += [kc]
        good = oc == ref and rc == len(ref) and sc == len(ref)
        ok &= good
        print(f"http n={n:6d} ok={good}", flush=True)
    print("ALL OK" if ok else "FAILURES")


if __name__ == "__main__":
    main()
