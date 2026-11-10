import ctypes
import sys

sys.path.insert(0, "bench/.simd-tmp")
from compare import load  # noqa: E402

L = load()
print("lib", L.lib())
print("codes base", hex(ctypes.cast(L._CODES, ctypes.c_void_p).value), len(L._CODES))
print("lens base", hex(ctypes.cast(L._LENGTHS, ctypes.c_void_p).value), len(L._LENGTHS))
print("codes[65]", L._CODES[65], "len[65]", L._LENGTHS[65])
