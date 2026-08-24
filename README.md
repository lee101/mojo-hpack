# mojo-hpack

HPACK header compression with its hottest byte-processing loops implemented in
[Mojo](https://www.modular.com/mojo). The Python package is named `hpack` and mirrors
the public API of the upstream Python
[`hpack`](https://github.com/python-hyper/hpack) package, so covered callers can switch
without changing imports.

The implemented scope is RFC 7541 header-block encoding and decoding: static and
dynamic tables, table-size updates, never-indexed fields, header-list size limits, raw
and Unicode output, integer representations, and the RFC Appendix B Huffman code.
Large Huffman encoding and decoding run in compiled Mojo; tiny fields use generated
Python fast paths to avoid FFI launch overhead. Tests compare exact wire bytes and
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
3.13.14. Times are the best of repeated runs on identical input; the short-field rows
use 20,000 repetitions and the batch and full-encoder rows use three.

| benchmark | mojo-hpack | upstream hpack | speedup |
| --- | ---: | ---: | ---: |
| Huffman encode 15 B | 2.14 us | 3.41 us | 1.60x |
| Huffman decode 12 B | 1.70 us | 3.69 us | 2.18x |
| Huffman encode 61.4 KB | 0.36 ms | 576.27 ms | 1618.76x |
| Huffman decode 52.5 KB | 1.81 ms | 17.00 ms | 9.37x |
| Huffman batch 4.2 MB | 13.60 ms | 1769.67 ms | 130.09x |
| Encoder 2,004 headers | 13.74 ms | 89.30 ms | 6.50x |

The unusually large encoding ratio is real: upstream builds one ever-growing Python
integer for the complete bitstream, so its cost grows steeply with long values. Typical
HTTP headers are short, where fixed ctypes call overhead reduces the advantage. The
full-encoder row uses 2,000 distinct metadata headers and includes Python table work and
all FFI crossings.

No GPU path is provided. Huffman coding has low arithmetic intensity and serial,
data-dependent bitstream state, so device transfer and launch overhead would dominate.
Large independent header fields use thresholded CPU parallelism instead.

## How it works

Python owns header state, immutable input bytes, result buffers, the canonical code
arrays, and a compact binary decode trie. ctypes passes their addresses as `Int` values
across the C ABI. The Mojo functions reconstruct `Pointer` values with
`AnyOrigin[mut=True]`, stream
codes through a bounded 64-bit accumulator, and write directly into caller-owned
contiguous byte buffers. Large header lists concatenate source fields once, make one
batched FFI call, and encode 64-field chunks in parallel above a 256-field and 1 MiB
threshold. The decoder traverses contiguous `Int32` child and symbol arrays, rejects EOS
symbols and invalid padding, and performs no allocation.
Nothing crosses the boundary as a Python object. The bridge rejects other buffer types,
validates addresses and signed lengths before pointer construction, obtains source and
destination byte-buffer addresses without copying, and checks returned lengths and batch
offsets before reading output. Inputs up to 32 bytes avoid FFI: encoding uses a bounded
Python integer and decoding uses a byte automaton generated from the canonical trie.

`MOJO_HPACK_LIB` can point at a prebuilt shared library when compilation at import time
is undesirable.

MIT licensed.
