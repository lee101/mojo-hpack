import ctypes
import sys

sys.path.insert(0, "bench/.simd-tmp")
from compare import Lib, load  # noqa: E402

L = load()
d = Lib("bench/.simd-tmp/dbg.so")
LENGTHS = L._LENGTHS
lengths = ctypes.addressof(LENGTHS)
idx = ctypes.create_string_buffer(b"\x01\x02\x03\x04", 4)
idx_addr = ctypes.addressof(idx)
print("size8", d.f("d_size8")(lengths, idx_addr), "expect", sum(LENGTHS[i] for i in (1, 2, 3, 4)), flush=True)
print("size8b", d.f("d_size8b")(lengths, idx_addr), flush=True)
