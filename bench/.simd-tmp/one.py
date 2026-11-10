import ctypes
import sys

sys.path.insert(0, "bench/.simd-tmp")
import ab
from hpack._lib import huffman_encode

B = ab.Bench("bench/.simd-tmp/base.so")
L = B.mod
lens = ctypes.addressof(L._LENGTHS)
codes = ctypes.addressof(L._CODES)
for data in (b"w", b"ww", b"www.example.com", ab.PAYLOAD):
    n = len(data)
    src = ctypes.create_string_buffer(data, n)
    ref = huffman_encode(data)
    out = ab.buffer_with_pad(len(ref))
    r = B.lib.mh_huffman_encode(ctypes.addressof(src), n, codes, lens, ctypes.addressof(out))
    print(n, "r", r, "want", len(ref), "match", out.raw[:r] == ref)
