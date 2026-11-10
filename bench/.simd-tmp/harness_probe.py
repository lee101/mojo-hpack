import ctypes, sys
sys.path.insert(0, "bench/.simd-tmp")
import ab
from hpack._lib import huffman_encode
L = ab.Bench("bench/.simd-tmp/base.so").mod
c = ctypes.CDLL("bench/.simd-tmp/cand.so")
c.k1_encode.argtypes = [ctypes.c_int64] * 5
c.k1_encode.restype = ctypes.c_int64
for data in (b"a", b"ab", b"www.example.com"):
    n = len(data)
    ref = huffman_encode(data)
    enc = ctypes.create_string_buffer(data, n)
    out = ab.buffer_with_pad(len(ref))
    r = c.k1_encode(ctypes.addressof(enc), n, ctypes.addressof(L._CODES), ctypes.addressof(L._LENGTHS), ctypes.addressof(out))
    print(n, "r", r, "want", len(ref), "match", out.raw[:r] == ref)
