import ctypes
import sys

sys.path.insert(0, "bench/.simd-tmp")
import ab
from hpack.huffman_constants import REQUEST_CODES_LENGTH

PAYLOAD = ab.PAYLOAD
for label, path in (("base", "bench/.simd-tmp/base.so"), ("variant", "bench/.simd-tmp/variant.so")):
    b = ab.Bench(path, "uint32")
    mod = b.mod
    src = ctypes.create_string_buffer(PAYLOAD, len(PAYLOAD))
    n = len(PAYLOAD)
    size = b.lib.mh_huffman_encoded_size(ctypes.addressof(src), n, ctypes.addressof(mod._LENGTHS))
    expect = (sum(REQUEST_CODES_LENGTH[c] for c in PAYLOAD) + 7) // 8
    print(label, "size", size, "expect", expect,
          "lengths[65]", mod._LENGTHS[65], "data[0]", PAYLOAD[0], flush=True)
