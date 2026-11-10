"""Reference points on this host: scalar lookup cost vs the current SIMD gather."""
import ctypes
import time

from hpack._lib import _LENGTHS, _bytes_address, lib

m = lib()
f = m.mh_huffman_encoded_size
data = b"content-type: application/json\r\n" * 2560


def cpu(fn, reps=100):
    fn()
    t = time.process_time()
    for _ in range(reps):
        fn()
    return (time.process_time() - t) / reps * 1e6


class Noop:
    def __init__(self, real):
        self.real = real

    def __call__(self, *a):
        s = time.process_time_ns()
        r = self.real(*a)
        Noop.ns += time.process_time_ns() - s
        return r

    ns = 0


for _ in range(3):
    print("size kernel      us", round(cpu(lambda: f(_bytes_address(data), len(data), ctypes.addressof(_LENGTHS))), 1))

# scalar table lookup in Python at the same length: ~30 ns/byte
st = time.perf_counter()
s = 0
for b in bytearray(data[:5000]):
    s += b
print("python sum 5KB    us", round((time.perf_counter() - st) * 1e6, 1))
print(open("/proc/loadavg").read().strip())
