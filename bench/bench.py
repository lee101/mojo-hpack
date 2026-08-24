"""Benchmarks Mojo Huffman kernels against upstream Python hpack."""

import importlib.util
import os
import platform
import sys
import time

import hpack
from hpack.huffman import HuffmanEncoder
from hpack.huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH
from hpack.huffman_table import decode_huffman
from hpack._lib import huffman_encode_many


def load_upstream():
    env_root = os.path.dirname(sys.executable)
    package = os.path.join(
        os.path.dirname(env_root), "lib", f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages", "hpack",
    )
    spec = importlib.util.spec_from_file_location(
        "_bench_upstream_hpack",
        os.path.join(package, "__init__.py"),
        submodule_search_locations=[package],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def best_time(function, repetitions=5):
    best = float("inf")
    result = None
    for _ in range(repetitions):
        start = time.perf_counter()
        result = function()
        best = min(best, time.perf_counter() - start)
    return best, result


def main():
    upstream = load_upstream()
    from _bench_upstream_hpack.huffman import HuffmanEncoder as UpstreamHuffmanEncoder
    from _bench_upstream_hpack.huffman_constants import REQUEST_CODES as UP_CODES
    from _bench_upstream_hpack.huffman_constants import REQUEST_CODES_LENGTH as UP_LENGTHS
    from _bench_upstream_hpack.huffman_table import decode_huffman as upstream_decode

    mojo_coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    upstream_coder = UpstreamHuffmanEncoder(UP_CODES, UP_LENGTHS)
    payload = (
        b"content-type: application/json; charset=utf-8\r\n"
        b"cache-control: no-cache\r\n"
        b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n"
    ) * 512
    encoded = mojo_coder.encode(payload)

    rows = []
    short_payload = b"www.example.com"
    short_encoded = mojo_coder.encode(short_payload)
    mojo_time, mojo_encoded = best_time(
        lambda: mojo_coder.encode(short_payload), 20_000
    )
    upstream_time, upstream_encoded = best_time(
        lambda: upstream_coder.encode(short_payload), 20_000
    )
    assert mojo_encoded == upstream_encoded
    rows.append((f"Huffman encode {len(short_payload)} B", mojo_time, upstream_time))

    mojo_time, mojo_decoded = best_time(lambda: decode_huffman(short_encoded), 20_000)
    upstream_time, upstream_decoded = best_time(
        lambda: upstream_decode(short_encoded), 20_000
    )
    assert mojo_decoded == upstream_decoded == short_payload
    rows.append((f"Huffman decode {len(short_encoded)} B", mojo_time, upstream_time))

    mojo_time, mojo_encoded = best_time(lambda: mojo_coder.encode(payload))
    upstream_time, upstream_encoded = best_time(lambda: upstream_coder.encode(payload))
    assert mojo_encoded == upstream_encoded
    rows.append((f"Huffman encode {len(payload) / 1000:.1f} KB", mojo_time, upstream_time))

    mojo_time, mojo_decoded = best_time(lambda: decode_huffman(encoded))
    upstream_time, upstream_decoded = best_time(lambda: upstream_decode(encoded))
    assert mojo_decoded == upstream_decoded == payload
    rows.append((f"Huffman decode {len(encoded) / 1000:.1f} KB", mojo_time, upstream_time))

    batch_values = [payload[:1024]] * 4_096
    mojo_time, mojo_batch = best_time(lambda: huffman_encode_many(batch_values), 3)
    upstream_time, upstream_batch = best_time(
        lambda: [upstream_coder.encode(value) for value in batch_values], 3
    )
    assert mojo_batch == upstream_batch
    rows.append(("Huffman batch 4.2 MB", mojo_time, upstream_time))

    headers = [
        (b":method", b"GET"),
        (b":scheme", b"https"),
        (b":path", b"/api/v1/resource"),
        (b":authority", b"example.test"),
    ] + [
        (f"x-meta-{i}".encode(), (b"metadata-value-" * 9) + str(i).encode())
        for i in range(2_000)
    ]
    mojo_time, mojo_block = best_time(lambda: hpack.Encoder().encode(headers), 3)
    upstream_time, upstream_block = best_time(lambda: upstream.Encoder().encode(headers), 3)
    assert mojo_block == upstream_block
    rows.append(("Encoder 2,004 headers", mojo_time, upstream_time))

    cpu = platform.processor()
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo") as stream:
            for line in stream:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    print(f"Machine: {cpu or platform.machine()}, Python {platform.python_version()}")
    print()
    print("| benchmark | mojo-hpack | upstream hpack | speedup |")
    print("| --- | ---: | ---: | ---: |")
    for name, mojo_time, upstream_time in rows:
        scale = 1_000_000 if max(mojo_time, upstream_time) < 0.001 else 1_000
        unit = "us" if scale == 1_000_000 else "ms"
        print(
            f"| {name} | {mojo_time * scale:.2f} {unit} | "
            f"{upstream_time * scale:.2f} {unit} | "
            f"{upstream_time / mojo_time:.2f}x |"
        )


if __name__ == "__main__":
    main()
