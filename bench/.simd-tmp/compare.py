"""Interleaved baseline/candidate timing through the ctypes bridge.

Usage: python compare.py BASE_MODE [LABEL LIBPATH]...
base mode is the checked-in library (built from git HEAD into dist/base.so).
"""
import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "python"))

HEADER = (
    b"content-type: application/json; charset=utf-8\r\n"
    b"cache-control: no-cache\r\n"
    b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n"
)
PAYLOAD = HEADER * 512


SIGS = {
    "mh_huffman_encoded_size": 3,
    "mh_huffman_encode": 5,
    "mh_huffman_decode": 7,
    "mh_huffman_encode_batch": 9,
}


class Lib:
    def __init__(self, path):
        self.cdll = ctypes.CDLL(path)
        for name, count in SIGS.items():
            try:
                fn = getattr(self.cdll, name)
            except AttributeError:
                continue
            fn.argtypes = [ctypes.c_int64] * count
            fn.restype = ctypes.c_int64

    def has(self, name):
        return hasattr(self.cdll, name)

    def f(self, name):
        return getattr(self.cdll, name)


def load():
    import hpack._lib as L

    return L


def cpu(fn, reps):
    fn()
    t = time.process_time()
    for _ in range(reps):
        fn()
    return (time.process_time() - t) / reps * 1e6


def build_cases(lib, L):
    codes = ctypes.addressof(L._CODES)
    lengths = ctypes.addressof(L._LENGTHS)
    left = ctypes.addressof(L._LEFT)
    right = ctypes.addressof(L._RIGHT)
    syms = ctypes.addressof(L._SYMBOLS)
    pa = L._bytes_address(PAYLOAD)
    n = len(PAYLOAD)
    size = lib.f("mh_huffman_encoded_size")(pa, n, lengths)
    dst = b"\0" * size
    da = L._bytes_address(dst)
    dec = b"\0" * (n + 16)
    deca = L._bytes_address(dec)
    batch = [PAYLOAD[:1024]] * 4096
    src = b"".join(batch)
    sa = L._bytes_address(src)
    offs = (ctypes.c_int64 * (len(batch) + 1))()
    p = 0
    for i, v in enumerate(batch):
        offs[i] = p
        p += len(v)
    offs[len(batch)] = p
    cap = (30 * p + 7 * len(batch)) // 8
    out = b"\0" * cap
    res = (ctypes.c_int64 * (len(batch) + 1))()
    cases = {
        "size 61.4 KB": (lambda: lib.f("mh_huffman_encoded_size")(pa, n, lengths), 200),
        "encode 61.4 KB": (lambda: lib.f("mh_huffman_encode")(pa, n, codes, lengths, da), 200),
        "decode 52.5 KB": (lambda: lib.f("mh_huffman_decode")(da, size, left, right, syms, deca, len(dec)), 100),
        "batch 4.2 MB": (
            lambda: lib.f("mh_huffman_encode_batch")(
                sa, ctypes.addressof(offs), len(batch), codes, lengths,
                L._bytes_address(out), cap, ctypes.addressof(res), 0,
            ),
            3,
        ),
    }
    cases["_keepalive"] = ((offs, out, res, dst, dec, src), 0)
    return cases


if __name__ == "__main__":
    L = load()
    libs = []
    for pair in sys.argv[1:]:
        label, path = pair.split("=", 1)
        if os.path.exists(path):
            libs.append((label, Lib(path)))
    cases = {label: build_cases(lib, L) for label, lib in libs}
    names = [k for k in next(iter(cases.values())) if not k.startswith("_")]
    print("# " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + open("/proc/loadavg").read().strip(), flush=True)
    print("| kernel | " + " | ".join(label for label, _ in libs) + " |", flush=True)
    for name in names:
        row = []
        for label, _ in libs:
            fn, reps = cases[label][name]
            row.append(cpu(fn, reps))
        best = min(row)
        cells = [f"{v:9.2f} us" + ("" if v == best else f" ({v / best:.2f}x)") for v in row]
        print(f"| {name} | " + " | ".join(cells) + " |", flush=True)
    print(open("/proc/loadavg").read().strip())
