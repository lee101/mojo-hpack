# mojo-hpack

HPACK header compression with its hottest byte-processing loops implemented in
[Mojo](https://www.modular.com/mojo). The Python package is named `hpack` and mirrors
the public API of the upstream Python
[`hpack`](https://github.com/python-hyper/hpack) package, so covered callers can switch
without changing imports.

The implemented scope is RFC 7541 header-block encoding and decoding: static and
dynamic tables, table-size updates, never-indexed fields, header-list size limits, raw
and Unicode output, integer representations, and the RFC Appendix B Huffman code.
Huffman encoding and decoding run in compiled Mojo. Tests compare exact wire bytes and
stateful behavior with upstream `hpack` 4.2.0 and exercise the published RFC request
and Huffman vectors.

## Install

```bash
pixi install
pixi run build
pixi run test
```

The shared library is written to `dist/libmojo-hpack.so`. Importing from a source checkout
also rebuilds it when `src/hpack.mojo` is newer. The supported installation is currently
a Linux source checkout managed by Pixi; no prebuilt wheel or non-Linux build is
provided.

## Usage

```python
from hpack import Decoder, Encoder, NeverIndexedHeaderTuple

headers = [
    (":method", "GET"),
    (":scheme", "https"),
    (":path", "/"),
    (":authority", "www.example.com"),
    NeverIndexedHeaderTuple("authorization", "Bearer secret"),
]

block = Encoder().encode(headers)
decoded = Decoder().decode(block)
assert decoded == [tuple(header) for header in headers]
```

Run the example through the managed environment from the repository root:

```bash
pixi run python - <<'PY'
from hpack import Decoder, Encoder

block = Encoder().encode([(":method", "GET"), (":path", "/")])
assert Decoder().decode(block) == [(":method", "GET"), (":path", "/")]
print(block.hex())
PY
```

## Coverage

Covered top-level upstream names are `Encoder`, `Decoder`, `HeaderTuple`,
`NeverIndexedHeaderTuple`, and the exception classes exported by upstream `hpack`
4.2.0. Tests prove stateful encoder/decoder parity, dynamic-table resizing and
eviction, sensitive fields, raw and Unicode decoding, list-size enforcement, invalid
table states and indices, integer-codec parity, malformed Huffman rejection, every
input octet, SIMD tails, and serial/parallel batch thresholds. The commonly imported
lower-level modules are present: `hpack.hpack` integer codecs, `hpack.table`,
`hpack.huffman`, `hpack.huffman_constants`, and `hpack.huffman_table`.

The dynamic-table policy and header representation logic remain in Python: they work on
small collections and are not useful compute kernels. Custom, non-RFC Huffman codebooks
are accepted by `HuffmanEncoder` for compatibility but use a pure-Python fallback. This
is an HPACK implementation, not an HTTP/2 framing or connection library. Private
upstream implementation details, its typing aliases, and its internal Huffman lookup
table are not compatibility targets.

## Benchmarks

Measured with `pixi run bench` on an Intel Xeon E5-2697 v4 at 2.30 GHz with Python
3.13.14. Times are the best of five runs on identical input (three for the full encoder).

| benchmark | mojo-hpack | upstream hpack | speedup |
| --- | ---: | ---: | ---: |
| Huffman encode 61.4 KB | 0.27 ms | 579.30 ms | 2130.80x |
| Huffman decode 52.5 KB | 1.84 ms | 16.85 ms | 9.13x |
| Encoder 2,004 headers | 34.80 ms | 126.57 ms | 3.64x |

The unusually large encoding ratio is real: upstream builds one ever-growing Python
integer for the complete bitstream, so its cost grows steeply with long values. Typical
HTTP headers are short, where fixed ctypes call overhead reduces the advantage. The
full-encoder row uses 2,000 distinct metadata headers and includes Python table work and
all FFI crossings.

No GPU path is provided. Large independent header fields use thresholded CPU
parallelism.

## How it works

Python owns header state, immutable input bytes, result buffers, the canonical code
arrays, and a
compact binary decode trie. ctypes passes their addresses as `Int` values across the C
ABI. The Mojo functions reconstruct `UnsafePointer` values with
`AnyOrigin[mut=True]`, stream codes through a bounded 64-bit accumulator, and write
directly into caller-owned contiguous byte buffers. Large header lists concatenate
source fields once, make one batched FFI call, and encode 64-field chunks in parallel
above a 256-field and 64 KiB threshold. The decoder traverses contiguous `Int32` child
and symbol arrays, rejects EOS symbols and invalid padding, and performs no allocation.
Nothing crosses the boundary as a Python object. The bridge rejects other buffer types,
validates addresses and signed lengths before pointer construction, keeps ctypes owners
alive for each call, and checks returned lengths and batch offsets before reading output.

`MOJO_HPACK_LIB` can point at a prebuilt shared library when compilation at import time
is undesirable.

MIT licensed.
