"""A/B harness: base library vs a variant library.

Both libraries are driven through hpack._lib wrappers built from a temp copy
whose `_LENGTHS` table is UInt32 (the pinned kernels read lengths as UInt32).
Every buffer handed to a library is writable, carries a canary pad, and is kept
alive. Timings use process CPU time because wall time is unreliable on this
shared host.
"""
import ctypes
import os
import sys
import time
import types

from hpack.huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEADER = (
    b"content-type: application/json; charset=utf-8\r\n"
    b"cache-control: no-cache\r\n"
    b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n"
)
PAYLOAD = HEADER * 512
BATCH = [PAYLOAD[:1024]] * 4096
PAD = 4096
SIGNATURES = {
    "mh_huffman_encoded_size": 3,
    "mh_huffman_encode": 5,
    "mh_huffman_decode": 7,
    "mh_huffman_encode_batch": 9,
}


def load_bridge():
    path = os.path.join(ROOT, "python", "hpack", "_lib.py")
    source = open(path).read()
    source = source.replace(
        "_LENGTHS = (ctypes.c_uint8 * len(REQUEST_CODES_LENGTH))(*REQUEST_CODES_LENGTH)",
        "_LENGTHS = (ctypes.c_uint32 * len(REQUEST_CODES_LENGTH))(*REQUEST_CODES_LENGTH)",
    )
    if "ctypes.c_uint32 * len(REQUEST_CODES_LENGTH)" not in source:
        raise RuntimeError("bridge source changed; update load_bridge")
    module = types.ModuleType(f"hpack._simd_{len(sys.modules)}")
    module.__package__ = "hpack"
    module.__file__ = path
    sys.modules[module.__name__] = module
    exec(compile(source, path, "exec"), module.__dict__)
    return module


_PAD_KEEP = []


def buffer_with_pad(size):
    total = size + PAD
    buf = ctypes.create_string_buffer(total if total > size else size)
    for i in range(size, total):
        buf[i] = 0xAA
    _PAD_KEEP.append(buf)
    return buf


def pad_intact(buf, size):
    return all(buf.raw[i] == 0xAA for i in range(size, size + PAD))


class Bench:
    def __init__(self, so_path):
        self.mod = load_bridge()
        self.mod.build = lambda force=False: so_path
        self.mod._loaded = None
        self.lib = ctypes.CDLL(so_path)
        for name, count in SIGNATURES.items():
            fn = getattr(self.lib, name)
            fn.argtypes = [ctypes.c_int64] * count
            fn.restype = ctypes.c_int64
        self.keep = []

    def addr(self, name):
        return ctypes.addressof(getattr(self.mod, name))

    def cases(self):
        sizes = []
        m = self.lib
        payload = ctypes.create_string_buffer(PAYLOAD, len(PAYLOAD))
        n = len(PAYLOAD)
        size = m.mh_huffman_encoded_size(ctypes.addressof(payload), n, self.addr("_LENGTHS"))
        enc = buffer_with_pad(size)
        written = m.mh_huffman_encode(
            ctypes.addressof(payload), n, self.addr("_CODES"), self.addr("_LENGTHS"),
            ctypes.addressof(enc))
        sizes.append(("encode 61.4 KB", size, written, pad_intact(enc, size)))
        dec = buffer_with_pad(n + 16)
        decoded = m.mh_huffman_decode(
            ctypes.addressof(enc), size, self.addr("_LEFT"), self.addr("_RIGHT"),
            self.addr("_SYMBOLS"), ctypes.addressof(dec), n + 16)
        sizes.append(("decode 52.5 KB", decoded, dec.raw[:decoded] == PAYLOAD, pad_intact(dec, n + 16)))

        src = ctypes.create_string_buffer(b"".join(BATCH), sum(len(v) for v in BATCH))
        offs = (ctypes.c_int64 * (len(BATCH) + 1))()
        p = 0
        for i, v in enumerate(BATCH):
            offs[i] = p
            p += len(v)
        offs[len(BATCH)] = p
        cap = (30 * p + 7 * len(BATCH)) // 8
        out = buffer_with_pad(cap)
        res = (ctypes.c_int64 * (len(BATCH) + 1))()
        total = m.mh_huffman_encode_batch(
            ctypes.addressof(src), ctypes.addressof(offs), len(BATCH), self.addr("_CODES"),
            self.addr("_LENGTHS"), ctypes.addressof(out), cap, ctypes.addressof(res), 0)
        sizes.append(("batch 4.2 MB", total, res[len(BATCH)], pad_intact(out, cap)))
        self.keep += [payload, enc, dec, src, offs, out, res]
        self.checks = sizes
        return {
            "size 61.4 KB": (lambda: m.mh_huffman_encoded_size(ctypes.addressof(payload), n, self.addr("_LENGTHS")), 300),
            "encode 61.4 KB": (lambda: m.mh_huffman_encode(ctypes.addressof(payload), n, self.addr("_CODES"), self.addr("_LENGTHS"), ctypes.addressof(enc)), 300),
            "decode 52.5 KB": (lambda: m.mh_huffman_decode(ctypes.addressof(enc), size, self.addr("_LEFT"), self.addr("_RIGHT"), self.addr("_SYMBOLS"), ctypes.addressof(dec), n), 200),
            "batch 4.2 MB": (lambda: m.mh_huffman_encode_batch(ctypes.addressof(src), ctypes.addressof(offs), len(BATCH), self.addr("_CODES"), self.addr("_LENGTHS"), ctypes.addressof(out), cap, ctypes.addressof(res), 0), 5),
        }


def cpu(fn, reps):
    fn()
    t = time.process_time()
    for _ in range(reps):
        fn()
    return (time.process_time() - t) / reps * 1e6


def run(specs, rounds=3):
    benches = {label: Bench(path) for label, path in specs}
    cases = {label: b.cases() for label, b in benches.items()}
    for label, b in benches.items():
        print(label, b.checks)
    names = list(next(iter(cases.values())))
    results = {name: {label: float("inf") for label in benches} for name in names}
    for _ in range(rounds):
        for name in names:
            for label in benches:
                fn, reps = cases[label][name]
                results[name][label] = min(results[name][label], cpu(fn, reps))
    labels = list(benches)
    print("# " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " load " +
          open("/proc/loadavg").read().strip())
    print("| kernel | " + " | ".join(labels) + " |")
    for name in names:
        best = min(results[name].values())
        cells = []
        for label in labels:
            v = results[name][label]
            mark = "" if v == best else f" ({v / best:.2f}x)"
            cells.append(f"{v:.2f} us{mark}")
        print(f"| {name} | " + " | ".join(cells) + " |")
    print("load " + open("/proc/loadavg").read().strip())


if __name__ == "__main__":
    base = os.path.join(ROOT, "bench/.simd-tmp/base.so")
    run([("base", base)] + [(os.path.basename(p), p) for p in sys.argv[1:]])
