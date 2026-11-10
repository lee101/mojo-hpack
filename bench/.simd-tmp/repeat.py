"""Machine check: is this host's timing stable enough to trust a 2x claim?"""
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


for i in range(3):
    print("size kernel us", round(cpu(lambda: f(_bytes_address(data), len(data), ctypes.addressof(_LENGTHS))), 1))
print(open("/proc/loadavg").read().strip())
