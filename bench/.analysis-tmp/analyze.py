"""ANALYZE-phase measurements for mojo-hpack.

Throwaway: lives under bench/.analysis-tmp (not tracked). Every number that
ends up in bench/analysis.md is produced by this script. Run under
`flock /tmp/mojo-bench.lock` only.
"""

import cProfile
import importlib.util
import io
import os
import pstats
import sys
import time
import tracemalloc

import numpy as np

# ---- mojo port ------------------------------------------------------------
import hpack as mojo_hpack
from hpack._lib import (
    LIB,
    huffman_decode,
    huffman_encode,
    huffman_encode_many,
)
from hpack.huffman import HuffmanEncoder, PYTHON_ENCODE_THRESHOLD
from hpack.huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH
from hpack.huffman_table import PYTHON_DECODE_THRESHOLD, decode_huffman

# ---- upstream -------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_upstream():
    env_root = os.path.dirname(sys.executable)
    package = os.path.join(
        os.path.dirname(env_root), "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages", "hpack",
    )
    spec = importlib.util.spec_from_file_location(
        "_bench_upstream_hpack", os.path.join(package, "__init__.py"),
        submodule_search_locations=[package],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


up = load_upstream()
from _bench_upstream_hpack.huffman import HuffmanEncoder as UpEncoder  # noqa: E402
from _bench_upstream_hpack.huffman_constants import (  # noqa: E402
    REQUEST_CODES as UP_CODES, REQUEST_CODES_LENGTH as UP_LENGTHS)
from _bench_upstream_hpack.huffman_table import decode_huffman as up_decode  # noqa: E402

mojo_coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
up_coder = UpEncoder(UP_CODES, UP_LENGTHS)


def best(fn, reps, warm=1):
    for _ in range(warm):
        fn()
    t = float("inf")
    for _ in range(reps):
        s = time.perf_counter()
        fn()
        t = min(t, time.perf_counter() - s)
    return t


def per_call(scalar_ns, reps):
    return scalar_ns / reps


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
HEADER = (
    b"content-type: application/json; charset=utf-8\r\n"
    b"cache-control: no-cache\r\n"
    b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n"
)
PAYLOAD = HEADER * 512                    # 61,440 B (bench.py "61.4 KB")
PAYLOAD_ENC = mojo_coder.encode(PAYLOAD)  # 52,508 B
SHORT = b"www.example.com"                # 15 B
SHORT_ENC = mojo_coder.encode(SHORT)      # 12 B
BATCH_VALUES = [PAYLOAD[:1024]] * 4096    # 4.2 MB
HEADERS = [
    (b":method", b"GET"), (b":scheme", b"https"),
    (b":path", b"/api/v1/resource"), (b":authority", b"example.test"),
] + [
    (f"x-meta-{i}".encode(), (b"metadata-value-" * 9) + str(i).encode())
    for i in range(2000)
]

SIZES = [4, 8, 15, 16, 32, 33, 64, 128, 256, 1024, 4096, 16384, 61440,
         262144, 1048576]
# repeat a realistic header line so every size has HTTP-like byte entropy
unit = HEADER


def at_size(n):
    reps = (n // len(unit)) + 1
    return (unit * reps)[:n]


results = []


def record(row):
    results.append(row)
    print("\t".join(str(x) for x in row), flush=True)


# ---------------------------------------------------------------------------
# 1. canonical bench.py workloads, all three columns
# ---------------------------------------------------------------------------
def scen_short_encode():
    for name, fn, reps in [
        ("mojo", lambda: mojo_coder.encode(SHORT), 20000),
        ("upstream", lambda: up_coder.encode(SHORT), 20000),
    ]:
        t = best(fn, reps)
        record(["scenario", f"Huffman encode 15 B [{name}]", 15, t, t / reps])


def scen_short_decode():
    for name, fn in [
        ("mojo", lambda: decode_huffman(SHORT_ENC)),
        ("upstream", lambda: up_decode(SHORT_ENC)),
    ]:
        reps = 20000
        t = best(fn, reps)
        record(["scenario", f"Huffman decode 12 B [{name}]", 12, t, t / reps])


def scen_payload():
    for name, fn, reps in [
        ("mojo-encode", lambda: mojo_coder.encode(PAYLOAD), 5),
        ("upstream-encode", lambda: up_coder.encode(PAYLOAD), 3),
        ("mojo-decode", lambda: decode_huffman(PAYLOAD_ENC), 5),
        ("upstream-decode", lambda: up_decode(PAYLOAD_ENC), 3),
    ]:
        t = best(fn, reps)
        record(["scenario", f"61.4 KB {name}", 61440, t, t / reps])


def scen_batch():
    for name, fn, reps in [
        ("mojo", lambda: huffman_encode_many(BATCH_VALUES), 3),
        ("upstream", lambda: [up_coder.encode(v) for v in BATCH_VALUES], 3),
        ("python-join-nocopy-guard",
         lambda: [mojo_coder.encode(v) for v in BATCH_VALUES], 3),
    ]:
        t = best(fn, reps)
        total = sum(len(v) for v in BATCH_VALUES)
        record(["scenario", f"batch 4096x1024 B [{name}]", total, t, t / reps])


def scen_encoder():
    for name, fn in [
        ("mojo", lambda: mojo_hpack.Encoder().encode(HEADERS)),
        ("upstream", lambda: up.Encoder().encode(HEADERS)),
    ]:
        reps = 3
        t = best(fn, reps)
        raw = sum(len(k) + len(v) for k, v in HEADERS)
        record(["scenario", f"Encoder 2004 headers [{name}]", raw, t, t / reps])


def scen_decoder():
    block = mojo_hpack.Encoder().encode(HEADERS)
    up_block = up.Encoder().encode(HEADERS)
    assert block == up_block

    def make_mojo():
        d = mojo_hpack.Decoder()
        d.decode(block)

    def make_up():
        d = up.Decoder()
        d.decode(up_block)

    for name, fn in [("mojo", make_mojo), ("upstream", make_up)]:
        t = best(fn, 5)
        raw = sum(len(k) + len(v) for k, v in HEADERS)
        record(["scenario", f"Decoder 2004 headers [{name}]", len(block), t, t / 5])


# ---------------------------------------------------------------------------
# 2. size sweep, port vs upstream vs python, all Huffman entry points
# ---------------------------------------------------------------------------
def sweep():
    for n in SIZES:
        data = at_size(n)
        reps = 20000 if n <= 64 else (2000 if n <= 4096 else (200 if n <= 65536
                                     else (20 if n <= 262144 else 5)))
        enc = mojo_coder.encode(data)
        assert enc == up_coder.encode(data)
        assert decode_huffman(enc) == data
        assert up_decode(enc) == data

        tm = best(lambda: huffman_encode(data), reps)
        record(["encode-lib", n, "mojo", tm, tm / reps])
        tm = best(lambda: mojo_coder.encode(data), reps)
        record(["encode-method", n, "mojo", tm, tm / reps])
        tu = best(lambda: up_coder.encode(data), reps)
        record(["encode-method", n, "upstream", tu, tu / reps])

        tm = best(lambda: huffman_decode(enc), reps)
        record(["decode-lib", n, "mojo", tm, tm / reps])
        tm = best(lambda: decode_huffman(enc), reps)
        record(["decode-fn", n, "mojo", tm, tm / reps])
        tu = best(lambda: up_decode(enc), reps)
        record(["decode-fn", n, "upstream", tu, tu / reps])

        # pure-Python baselines for both kernels (no FFI at all)
        tp = best(lambda: HuffmanEncoder.encode_py(mojo_coder, data), reps)
        record(["encode-py", n, "python", tp, tp / reps])
        tp = best(lambda: decode_huffman_py(enc), reps)
        record(["decode-py", n, "python", tp, tp / reps])


import hpack.huffman as _hm  # noqa: E402
import hpack.huffman_table as _ht  # noqa: E402


def _encode_py(self, data):
    value = 0
    width = 0
    codes = self.huffman_code_list
    lengths = self.huffman_code_list_lengths
    for byte in data:
        bits = lengths[byte]
        value = (value << bits) | codes[byte]
        width += bits
    padding = (-width) % 8
    value = (value << padding) | ((1 << padding) - 1)
    return value.to_bytes((width + padding) // 8, "big")


def _decode_short(data):
    table = _ht._BYTE_DECODER
    row = 0
    decoded = bytearray()
    for value in data:
        row, emitted = table[row][value]
        if row < 0:
            from hpack.exceptions import HPACKDecodingError
            raise HPACKDecodingError("Invalid Huffman string")
        if emitted:
            decoded.extend(emitted)
    return bytes(decoded)


HuffmanEncoder.encode_py = _encode_py
decode_huffman_py = _decode_short


# ---------------------------------------------------------------------------
# 3. glue vs kernel
# ---------------------------------------------------------------------------
def glue_kernel():
    """Kernel time from C-level (cumtime-proxy) split, done two ways."""
    from hpack import _lib

    for n in [15, 33, 256, 4096, 61440, 1048576]:
        data = at_size(n)
        reps = 2000 if n <= 4096 else (200 if n <= 61440 else 20)

        # --- tail-slice copy cost alone (same size the decoder/py path pays)
        out = b"x" * n
        slow = b"y" * (n + 7)
        t = best(lambda: out[: n - 3], reps)
        record(["glue", f"bytes tail-slice {n}B", n, t, t / reps])
        t = best(lambda: slow[len(slow) - n:], reps)
        record(["glue", f"bytes slice-near-end {n}B", n, t, t / reps])

        # --- 1. pure python glue around an empty kernel, decoded by difference:
        # measure python encode path with kernel replaced by a no-op
        saved_size = _lib.mh_huffman_encoded_size if hasattr(_lib, "mh_huffman_encoded_size") else None
        real_lib = _lib.lib
        calls = {"n": 0}

        class FakeFn:
            def __init__(self, real):
                self.real = real

            def __call__(self, *a):
                calls["n"] += 1
                return self.real(*a)

        fake = type("L", (), {})()
        for nm in ["mh_huffman_encoded_size", "mh_huffman_encode"]:
            setattr(fake, nm, FakeFn(getattr(real_lib, nm)))
        _lib.lib = lambda: fake
        t_ffi = best(lambda: huffman_encode(data), reps)
        _lib.lib = real_lib
        calls["n"] = 0
        t_real = best(lambda: huffman_encode(data), reps)
        kernel = t_real - t_ffi
        record(["split", f"encode {n}B total", n, t_real, t_real / reps])
        record(["split", f"encode {n}B glue(wrapper)", n, t_ffi, t_ffi / reps])
        record(["split", f"encode {n}B kernel(call-diff)", n, kernel, kernel / reps])

        enc = mojo_coder.encode(data)
        # no-op kernel: return the real decoded length so the glue path,
        # including its tail slice, is exercised identically.
        plain_n = len(_decode_short(enc))

        fake2 = type("L", (), {})()
        fake2.mh_huffman_decode = lambda *a: plain_n

        _lib.lib = lambda: fake2
        t_ffi = best(lambda: huffman_decode(enc), reps)
        _lib.lib = real_lib
        t_real = best(lambda: huffman_decode(enc), reps)
        record(["split", f"decode {n}B input total", n, t_real, t_real / reps])
        record(["split", f"decode {n}B input glue(wrapper)", n, t_ffi, t_ffi / reps])
        record(["split", f"decode {n}B input kernel(call-diff)", n,
                t_real - t_ffi, (t_real - t_ffi) / reps])


# ---------------------------------------------------------------------------
# 4. profiler attribution: python frames vs the C call
# ---------------------------------------------------------------------------
def profile_entry(profile_block):
    """cProfile percentage of wall time in Python frames vs C calls."""
    pr = cProfile.Profile()
    # prime the lib so import/build isn't in the profile
    huffman_encode(PAYLOAD)
    pr.enable()
    REPEATS = 30
    for _ in range(REPEATS):
        pass
    pr.disable()
    return pr


def profile_hot(entry, reps, label):
    huffman_encode(PAYLOAD)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(reps):
        entry()
    pr.disable()
    st = pstats.Stats(pr)
    tot = st.total_tt
    rows = []
    for (fn, lineno, name), (cc, nc, tt, ct, _callers) in st.stats.items():
        rows.append((ct, name, fn))
    rows.sort(reverse=True)
    py_only = sum(r[0] for r in rows if r[1] in (
        "encode", "decode_huffman", "huffman_encode", "huffman_decode",
        "_decode_short", "add", "search", "_encode_literal", "_to_bytes",
        "encode_integer", "_decode_literal", "_unicode_if_needed",
        "huffman_encode_many", "_decode_literal_index",
        "_decode_literal_no_index", "_encode_indexed_literal", "_bytes_address",
        "_allocate_bytes", "table_entry_size", "get_by_index",
        "_encode_indexed", "decode", "_decode_indexed", "HeaderTable",
        "add", "_shrink", "_encoded_size"))
    print(f"\n[profile] {label} reps={reps} total={tot:.3f}s "
          f"python-attributed={py_only:.3f}s "
          f"({100 * py_only / tot:.1f}%)")
    for ct, name, fn in rows[:12]:
        print(f"   {100 * ct / tot:6.1f}%  {ct:8.3f}s  {name}  ({os.path.basename(fn)})")


def profiled():
    profile_hot(lambda: mojo_coder.encode(SHORT), 40000, "encode 15B")
    profile_hot(lambda: decode_huffman(SHORT_ENC), 40000, "decode 12B")
    profile_hot(lambda: mojo_coder.encode(PAYLOAD), 40, "encode 61.4KB")
    profile_hot(lambda: decode_huffman(PAYLOAD_ENC), 40, "decode 52.5KB")
    profile_hot(lambda: huffman_encode(PAYLOAD), 40, "encode kernel only 61.4KB")
    profile_hot(lambda: mojo_hpack.Encoder().encode(HEADERS), 10, "Encoder 2004")
    block = mojo_hpack.Encoder().encode(HEADERS)
    profile_hot(lambda: mojo_hpack.Decoder().decode(block), 10, "Decoder 2004")


# ---------------------------------------------------------------------------
# 5. allocation / copy accounting
# ---------------------------------------------------------------------------
def allocs():
    def measure(label, fn, reps=1):
        fn()
        tracemalloc.start()
        fn()
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        record(["alloc", label, "", peak, ""])

    measure("encode 15B peak bytes", lambda: mojo_coder.encode(SHORT))
    measure("encode 61.4KB peak bytes", lambda: mojo_coder.encode(PAYLOAD))
    measure("decode 12B in peak bytes", lambda: decode_huffman(SHORT_ENC))
    measure("decode 52.5KB in peak bytes", lambda: decode_huffman(PAYLOAD_ENC))
    measure("batch 4.2MB peak bytes", lambda: huffman_encode_many(BATCH_VALUES))
    measure("Encoder 2004 peak bytes",
            lambda: mojo_hpack.Encoder().encode(HEADERS))
    block = mojo_hpack.Encoder().encode(HEADERS)
    measure("Decoder 2004 peak bytes",
            lambda: mojo_hpack.Decoder().decode(block))

    # copy accounting: count bytes produced by the tail slice on the decoder path
    for name, n in [("decode 12B", 12), ("decode 52.5KB", len(PAYLOAD_ENC)),
                    ("encode 15B (py path)", 15)]:
        pass

    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    tracemalloc.stop()


def gen_timings():
    out = {}
    for n in [15, 16, 32, 33, 64, 256, 1024, 4096]:
        data = at_size(n)
        reps = 20000 if n <= 64 else 5000
        t = best(lambda: HuffmanEncoder.encode_py(mojo_coder, data), reps)
        out[n] = t / reps
        print(f"[py-encode] {n}B {t / reps * 1e9:.0f} ns", flush=True)
    return out


MODES = {
    "scenario": scen_short_encode,
}

if __name__ == "__main__":
    which = sys.argv[1:] or ["scenario", "sweep", "glue", "profiled", "allocs"]
    print(f"# python {sys.version.split()[0]}  lib {LIB}")
    print(f"# {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    for part in which:
        if part == "scenario":
            scen_short_encode()
            scen_short_decode()
            scen_payload()
            scen_batch()
            scen_encoder()
            scen_decoder()
        elif part == "sweep":
            sweep()
        elif part == "glue":
            glue_kernel()
        elif part == "profiled":
            profiled()
        elif part == "allocs":
            allocs()
        elif part == "pygen":
            gen_timings()
