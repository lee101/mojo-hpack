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
use 20,000 repetitions and the batch and full-encoder rows use three. The host is shared
with other workloads, so these are medians of three full bench runs with the observed
spread noted where it is material.

| benchmark | mojo-hpack | upstream hpack | speedup |
| --- | ---: | ---: | ---: |
| Huffman encode 15 B | 2.30 us | 3.65 us | 1.59x |
| Huffman decode 12 B | 1.89 us | 3.95 us | 2.09x |
| Huffman encode 61.4 KB | 0.22 ms | 578.91 ms | 2622.42x |
| Huffman decode 52.5 KB | 1.43 ms | 17.19 ms | 11.89x |
| Huffman batch 4.2 MB | 16.73 ms | 1801.56 ms | 107.70x |
| Encoder 2,004 headers | 13.03 ms | 88.92 ms | 6.76x |

The encoder row spread across the three runs (12.89 to 28.59 ms) tracks host load, not
the code; it stays on the serial path either way. To separate the parallelism change
from that noise, the batch and encoder rows were also run back to back with the
parallel threshold disabled: batch 4.2 MB went from 23.73 ms to 16.67 ms (1.42x) and
the 2,004-header encoder row was flat at 13.59 against 13.03 ms.

The unusually large encoding ratio is real: upstream builds one ever-growing Python
integer for the complete bitstream, so its cost grows steeply with long values. Typical
HTTP headers are short, where fixed ctypes call overhead reduces the advantage. The
full-encoder row uses 2,000 distinct metadata headers and includes Python table work and
all FFI crossings.

No GPU path is provided. Huffman coding has low arithmetic intensity and serial,
data-dependent bitstream state, so device transfer and launch overhead would dominate.

## Parallelism

Only the batched field encoder is parallelised. Huffman encoding of one field is a
serial bitstream, but distinct fields write disjoint ranges of the output buffer, so
64-field chunks are independent work items. `mh_huffman_encode_batch` runs them with
`parallelize` from `max.algorithm` when the caller passes a worker count of 2 or more
(`parallelize(fn, chunks, workers)`, with a nested `def` worker). `hpack._lib` requests
4 workers only when a batch reaches 256 fields **and** 2 MiB; everything else, including
the whole single-field encode/decode path, stays serial.

Measurements below are from this host, an Intel Xeon E5-2697 v4 (72 logical cores) that
is shared with other workloads, so run-to-run spread is real and is reported rather than
smoothed away. Each cell is the best of repeated runs of the same batch.

Crossover, batch encoder only, serial vs 4 workers, 60 B fields:

| total bytes | fields | serial | 4 workers | result |
| ---: | ---: | ---: | ---: | --- |
| 65 KB | 1,092 | 0.73 ms | 5.07 ms | severe loss |
| 131 KB | 2,184 | 1.67 ms | 5.85 ms | severe loss |
| 262 KB | 4,369 | 2.93 ms | 5.62 ms | loss |
| 524 KB | 8,738 | 5.85 ms | 6.60 ms | loss |
| 1 MiB | 17,476 | 11.60 ms | 9.70 ms | marginal, within spread (0.85x to 1.20x across runs) |
| 2 MiB | 34,952 | 23.40 ms | 15.44 ms | win, 1.52x |
| 4 MiB | 69,905 | 46.67 ms | 26.01 ms | win, 1.79x |
| 8 MiB | 139,810 | 93.35 ms | 52.88 ms | win, 1.83x |

The shape is the same for 16 B and 1 KB fields, with the crossover in the same
512 KB to 1 MiB band. Two effects set the floor: each parallel launch itself costs about
11 us (measured with a no-op worker, independent of payload), and a fixed 64-field chunk
means small batches offer little work to spread. The old shipped threshold was 1 MiB,
where four workers only tied serial; the reviewed threshold is 2 MiB, one doubling of
margin above the measured crossover.

Worker count, best of 5, after the threshold (this build uses a cap of 4, so 8 and 16
were measured with a temporary cap of 16 for information only):

| total bytes | serial | 1 worker | 2 workers | 4 workers | 8 workers | 16 workers |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 47.33 ms | 47.08 ms | 36.56 ms | 26.29 ms | 21.08 ms | 16.23 ms |
| 16 MiB | 189.88 ms | 189.23 ms | 114.01 ms | 85.58 ms | 61.24 ms | 51.54 ms |

Two worker columns describe a measured outcome, not a measurement mistake: 2 workers is
often the *worst* setting, below serial and well below 4. Over 9-repeat sweeps it lands
between 0.45x and 1.17x of serial, while 4 workers at the same sizes are between 1.15x
and 1.60x. Index distribution is not the cause: 274 chunks are handed out exactly once
and evenly spread at both 2 and 4 workers. A compute-bound synthetic loop scales cleanly
at 2 workers (12.5 ms against an ideal 12.8 ms), so the gap is specific to this kernel,
whose per-byte cost is low enough that worker start-up and scheduling dominate when only
two workers are covering the batch. Whatever the cause, the effect is stable across
repeats and field sizes, so the bridge never asks for 2.

Above 4 workers the batch keeps improving (2.7x to 3.5x at 16 workers in the temporary
cap runs). The worker cap is kept at 4 anyway: this host is shared, the gains continue
well into other tenants' capacity, and the requirement was to prove more helps before
raising it. The numbers above are the evidence for a later pass that wants to raise it.

End to end through `Encoder().encode`, the win is much smaller than the batch numbers,
because Huffman is only part of encoder time and each field is looked up in the header
table serially:

| headers | bytes | serial path | parallel path | speedup |
| ---: | ---: | ---: | ---: | ---: |
| 16,000 | 2.41 MB | 107.2 ms | 106.1 ms | 1.01x |
| 32,000 | 4.84 MB | 221.3 ms | 215.4 ms | 1.03x |
| 64,000 | 9.71 MB | 456.1 ms | 446.8 ms | 1.02x |

The benchmark's own `Encoder 2,004 headers` row (about 0.3 MB) stays on the serial path
by design and is unaffected.

Parity is covered by `tests/test_huffman.py`: the same values are encoded with 1 worker
and with 2 to 4 workers and compared byte for byte, across chunk-boundary field counts
and 3 B, 60 B, and 1 KB field widths, and the threshold test straddles 2 MiB.

The same comparison through the bridge (`huffman_encode_many`), best of several sweeps,
4 workers against the serial path. These are smaller than the numbers above because the
bridge's own work (concatenating fields, building offsets, slicing the result back into
per-field bytes) is serial and does not shrink:

| fields | bytes | serial | 4 workers | speedup |
| ---: | ---: | ---: | ---: | ---: |
| 34,952x60 B | 2.10 MB | 66.21 ms | 53.06 ms | 1.25x |
| 139,810x60 B | 8.39 MB | 265.71 ms | 208.86 ms | 1.27x |
| 4,096x1024 B | 4.19 MB | 57.12 ms | 35.41 ms | 1.61x |
| 16,384x1024 B | 16.78 MB | 281.87 ms | 119.44 ms | 2.36x |

One caveat on the benchmark's own `Huffman batch 4.2 MB` row: that workload is 4,096
fields of 1 KB, a favourable shape for parallel work. Whole-header-list traffic with
many short fields is closer to the 60 B rows, where the win is about 1.25x. A batch
below the threshold is unaffected and stays on the serial path by design.

## How it works

Python owns header state, immutable input bytes, result buffers, the canonical code
arrays, and a compact binary decode trie. ctypes passes their addresses as `Int` values
across the C ABI. The Mojo functions reconstruct `Pointer` values with
`AnyOrigin[mut=True]`, stream
codes through a bounded 64-bit accumulator, and write directly into caller-owned
contiguous byte buffers. Large header lists concatenate source fields once, make one
batched FFI call, and encode independent 64-field chunks with `parallelize` from
`max.algorithm` once a batch reaches 256 fields and 2 MiB (see
[Parallelism](#parallelism) for why that threshold is where it is). The decoder
traverses contiguous `Int32` child and symbol arrays, rejects EOS
symbols and invalid padding, and performs no allocation.
Nothing crosses the boundary as a Python object. The bridge rejects other buffer types,
validates addresses and signed lengths before pointer construction, obtains source and
destination byte-buffer addresses without copying, and checks returned lengths and batch
offsets before reading output. Inputs up to 32 bytes avoid FFI: encoding uses a bounded
Python integer and decoding uses a byte automaton generated from the canonical trie.

`MOJO_HPACK_LIB` can point at a prebuilt shared library when compilation at import time
is undesirable.

MIT licensed.
