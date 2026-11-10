"""Microbench + correctness for candidate kernels exported from cand.so."""
import ctypes
import random
import sys
import time

sys.path.insert(0, "bench/.simd-tmp")
import ab
from hpack._lib import huffman_encode, huffman_decode

L = ab.load_bridge()
cand = ctypes.CDLL("bench/.simd-tmp/cand.so")
for name in ("k1_decode", "k2_decode"):
    fn = getattr(cand, name)
    fn.argtypes = [ctypes.c_int64] * 7
    fn.restype = ctypes.c_int64
for name in ("k1_encode", "k2_encode", "k3_encode"):
    fn = getattr(cand, name)
    fn.argtypes = [ctypes.c_int64] * 5
    fn.restype = ctypes.c_int64

lengths = ctypes.addressof(L._LENGTHS)
codes = ctypes.addressof(L._CODES)
left = ctypes.addressof(L._LEFT)
right = ctypes.addressof(L._RIGHT)
syms = ctypes.addressof(L._SYMBOLS)
PAYLOAD = ab.PAYLOAD


def check():
    ok = True
    rng = random.Random(3)
    sizes = (1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 127, 128, 129, 1000, 65_537)
    for n in sizes:
        for data in (rng.randbytes(n), (PAYLOAD * 2)[:n]):
            ref = huffman_encode(data)
            enc = ctypes.create_string_buffer(data, n)
            out = ab.buffer_with_pad(len(ref))
            for name in ("k1_encode", "k2_encode", "k3_encode"):
                written = getattr(cand, name)(ctypes.addressof(enc), n, codes, lengths, ctypes.addressof(out))
                good = written == len(ref) and out.raw[:written] == ref and ab.pad_intact(out, len(ref))
                ok &= good
                if not good:
                    print("ENCODE FAIL", name, n, written, len(ref))
            src = ctypes.create_string_buffer(ref, len(ref))
            dec = ab.buffer_with_pad(n + 16)
            for name in ("k1_decode", "k2_decode"):
                got = getattr(cand, name)(ctypes.addressof(src), len(ref), left, right, syms, ctypes.addressof(dec), n + 16)
                good = got == n and dec.raw[:got] == data and ab.pad_intact(dec, n + 16)
                ok &= good
                if not good:
                    print("DECODE FAIL", name, n, got)
    # malformed / capacity behaviour must match base error codes
    for bad in (b"\xff", b"\x00", b"\xff\xff\xff\xff", b"\x00\x00\x00\x00"):
        src = ctypes.create_string_buffer(bad, len(bad))
        dec = ab.buffer_with_pad(64)
        got = cand.k2_decode(ctypes.addressof(src), len(bad), left, right, syms, ctypes.addressof(dec), 64)
        print("bad", bad.hex(), "->", got, flush=True)
    print("ALL OK" if ok else "FAILURES", flush=True)


def cpu(fn, reps):
    fn()
    t = time.process_time()
    for _ in range(reps):
        fn()
    return (time.process_time() - t) / reps * 1e6


def bench():
    n = len(PAYLOAD)
    ref = huffman_encode(PAYLOAD)
    src = ctypes.create_string_buffer(PAYLOAD, n)
    enc = ctypes.create_string_buffer(ref, len(ref))
    out = ab.buffer_with_pad(len(ref))
    b = ab.Bench("bench/.simd-tmp/base.so")
    dec = ab.buffer_with_pad(n + 16)
    res = {name: float("inf") for name in ("k1_encode", "k2_encode", "k3_encode", "k1_decode", "k2_decode")}
    res["base_encode"] = res["base_decode"] = float("inf")
    for _ in range(3):
        res["base_encode"] = min(res["base_encode"], cpu(lambda: b.lib.mh_huffman_encode(ctypes.addressof(src), n, codes, lengths, ctypes.addressof(out)), 300))
        res["base_decode"] = min(res["base_decode"], cpu(lambda: b.lib.mh_huffman_decode(ctypes.addressof(enc), len(ref), left, right, syms, ctypes.addressof(dec), n + 16), 200))
        for name in ("k1_encode", "k2_encode", "k3_encode"):
            f = getattr(cand, name)
            res[name] = min(res[name], cpu(lambda: f(ctypes.addressof(src), n, codes, lengths, ctypes.addressof(out)), 300))
        for name in ("k1_decode", "k2_decode"):
            f = getattr(cand, name)
            res[name] = min(res[name], cpu(lambda: f(ctypes.addressof(enc), len(ref), left, right, syms, ctypes.addressof(dec), n + 16), 200))
    print("load", open("/proc/loadavg").read().strip())
    for k, v in res.items():
        print(f"{k:14s} {v:8.1f} us")


if __name__ == "__main__":
    if "--bench" in sys.argv:
        bench()
    else:
        check()
