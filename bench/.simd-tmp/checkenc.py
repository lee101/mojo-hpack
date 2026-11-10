"""Correctness check of encode kernels: variant vs bridge reference."""
import ctypes
import random
import sys

sys.path.insert(0, "bench/.simd-tmp")
import ab
from hpack._lib import huffman_encode

PAYLOAD = ab.PAYLOAD


def check(path):
    b = ab.Bench(path)
    mod = b.mod
    ok = True
    rng = random.Random(11)
    LENGTHS = mod._LENGTHS
    CODES = mod._CODES
    lengths = ctypes.addressof(LENGTHS)
    codes = ctypes.addressof(CODES)
    for n in (1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 127, 128, 1000, 65_537):
        for data in (rng.randbytes(n), (PAYLOAD * 2)[:n]):
            ref = huffman_encode(data)
            src = ctypes.create_string_buffer(data, n)
            size = b.lib.mh_huffman_encoded_size(ctypes.addressof(src), n, lengths)
            out = ab.buffer_with_pad(size)
            written = b.lib.mh_huffman_encode(ctypes.addressof(src), n, codes, lengths, ctypes.addressof(out))
            good = size == len(ref) and written == len(ref) and out.raw[:written] == ref and ab.pad_intact(out, size)
            ok &= good
            if not good:
                print("FAIL", path, n, size, written, len(ref))
    print(path, "OK" if ok else "FAILURES")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        check(p)
