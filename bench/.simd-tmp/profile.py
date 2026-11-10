"""Throwaway attribution for the SIMD phase: kernel time vs bridge time."""
import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "python"))

import hpack._lib as L  # noqa: E402

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


def split(label, fn, reps, noop_names):
    real = L.lib()
    fake = type("L", (), {})()
    calls = {"n": 0, "t": 0.0}

    def wrap(name):
        impl = getattr(real, name)

        def call(*a):
            s = time.perf_counter()
            r = impl(*a)
            calls["t"] += time.perf_counter() - s
            calls["n"] += 1
            return r

        return call

    for name in noop_names:
        setattr(fake, name, wrap(name))
    L._loaded = fake
    total = best(fn, reps)
    L._loaded = real
    real_total = best(fn, reps)
    print(f"{label:28s} total {real_total*1e6:9.2f} us  kernel {calls['t']/reps*1e6:9.2f} us  "
          f"({calls['t']/real_total*100:5.1f}%)  calls/run {calls['n']/max(reps,1):.0f}")


if __name__ == "__main__":
    print(f"# {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    split("encode 61.4 KB", lambda: L.huffman_encode(PAYLOAD), 200,
          ["mh_huffman_encoded_size", "mh_huffman_encode"])
    enc = L.huffman_encode(PAYLOAD)
    split("decode 52.5 KB", lambda: L.huffman_decode(enc), 200, ["mh_huffman_decode"])
    split("batch 4096x1 KB", lambda: L.huffman_encode_many(BATCH), 5,
          ["mh_huffman_encode_batch"])
    short = b"www.example.com"
    split("encode 15 B", lambda: L.huffman_encode(short), 20000,
          ["mh_huffman_encoded_size", "mh_huffman_encode"])
