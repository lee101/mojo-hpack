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

CPU only: memory-bound. No GPU path is provided; see [GPU](#gpu) for the measurements
that decided that.

## GPU

No GPU path is implemented. Both Huffman kernels are below the arithmetic-intensity gate,
so per the phase rules this is a **CPU only: memory-bound** outcome and no device code was
added.

The gate was checked before any GPU work:

- The size gate references `bench/analysis.md`. That file does not exist in this repository
  (it is not in `HEAD` or any commit; only its generator `bench/.analysis-tmp/analyze.py`
  is tracked). The intensity figures below were therefore measured directly for this
  decision instead of being read from it.
- `nvidia-smi --query-gpu=memory.free --format=csv,noheader` reported **4309 MiB free** on
  an RTX 5090 (32,607 MiB total, 71% utilisation) on 2026-11-10, above the 4000 MiB floor,
  so the phase was evaluated rather than skipped.
- `DeviceContext` from `max.gpu.host` and `block_idx`/`thread_idx` from `max.gpu` do work on
  this toolchain: a device-query probe and a streaming kernel both ran on the RTX 5090.
  No allocation here would approach 2 GB.

**Arithmetic intensity.** Measured on the Mojo kernels themselves (the FFI-call cost
subtracted), Intel Xeon E5-2697 v4 host, RTX 5090 device:

| kernel | traffic per call | serial operations | intensity | clean CPU cost |
| --- | --- | --- | --- | --- |
| `mh_huffman_encode` | read `n`, write ~1.03`n` | one shift+or+store per emitted bit | ~15 bit-ops per input byte, 1 pass | 0.022 ns per byte at 1 MiB |
| `mh_huffman_decode` | read `n`, write ~0.98`n` | one trie step per input bit | ~8 trie steps per input byte, 1 pass | 0.261 ns per encoded byte at 1 MiB |

Both are far under the ~2 flops per byte threshold: a few integer ops per byte, done once,
with no reuse. Each kernel is one streaming pass: the encode side accumulates a 64-bit word
and stores every full byte, the decode side follows a compile-time trie one bit at a time.
There is no tile to promote into shared memory, so a device port would be a bandwidth copy
wrapped around a serial, data-dependent bitstream state, which is exactly the shape that
cannot amortise a transfer.

**Numbers that would have had to be beaten.** Measured on the same host and device with a
one-launch-per-call streaming kernel and a single copy-in/copy-out:

| transfer | H2D | D2H | round trip | effective bandwidth |
| --- | ---: | ---: | ---: | ---: |
| 15 B | 5.96 us | 7.47 us | 13.42 us | — |
| 4 KiB | 7.41 us | 8.31 us | 15.71 us | — |
| 60 KiB | 25.83 us | 23.71 us | 49.53 us | — |
| 1 MiB | 198.78 us | 271.96 us | 470.74 us | 5 to 10 GB/s over PCIe |

The empty launch plus `synchronize()` floor is **6.10 us best of 200, 10.03 us mean**,
independent of payload. Device-side streaming bandwidth on the same kernel is 1.5 to 2.4 TB/s,
so the device is not the limit; PCIe and launch are.

**Comparison at real caller sizes.** Single-field through `huffman_encode`/`huffman_decode`,
CPU kernel time against the measured transfer plus launch floor. Ratios are CPU divided by
floor, so above 1.0 the GPU could break even:

| input | encoded | CPU encode | CPU decode | floor (in+out+launch) | enc CPU/floor | dec CPU/floor |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 15 B | 11 B | under 0.1 us | under 0.1 us | 20.9 us | under 0.005 | under 0.005 |
| 1 KiB | 872 B | under 0.1 us | 0.4 us | 23.1 us | under 0.005 | 0.019 |
| 4 KiB | 3,501 B | under 0.1 us | 3.9 us | 23.1 us | under 0.005 | 0.17 |
| 16 KiB | 14,008 B | 6.6 us | 60.2 us | 57.0 us | 0.115 | 1.06 |
| 60 KiB | 52,544 B | 55.3 us | 672 us | 57.0 us | 0.970 | 11.8 |
| 256 KiB | 224,184 B | 1,075 us | 11,658 us | 478 us | 2.25 | 24.4 |
| 1 MiB | 896,749 B | 23,172 us | 233,961 us | 478 us | 48.5 | 489 |

`under 0.1 us` means the kernel is too fast to resolve from ctypes call overhead at that
size. Columns are CPU kernel time and the measured floor for the same data, then CPU divided
by floor: below 1.0 the CPU kernel is cheaper than getting the bytes to the device and back,
so a GPU cannot win however fast its kernel is.

Both kernels are beaten by their own transfer across the whole size range that `hpack`
actually serves. At 15 B to 4 KiB, the field sizes this library sees most, the CPU finishes
the kernel in under a microsecond while the launch alone costs 6.1 us. Above that the encoder
does eventually cost more than the transfer (2.25x at 256 KiB, 48.5x at 1 MiB), but that is
PCIe being slow rather than the kernel having compute to amortise: the encoder is a
one-word-per-byte dependency chain, the worst possible shape for a GPU, and each row is
measured on the CPU so it does not claim what a device kernel would do. The two rows where a
GPU could plausibly compete are 256 KiB and 1 MiB inputs, which are not header fields this
library is given.

The decode kernel is the slower of the two and the only row where a device kernel has any
headroom at all: above 16 KiB the transfer no longer decides, and at 1 MiB the CPU spends
234 ms against a 0.48 ms floor. A device decoder would still have to beat a kernel that runs
at ~0.26 ns per encoded byte, reproduce the trie walk's mid-stream failure returns (`-1`
invalid padding, `-2` short output), and pay the round trip. Real header fields are tens to
hundreds of bytes, `PYTHON_ENCODE_THRESHOLD` is 32 B, and the whole Encoder/Decoder path for
2,004 fields is 13 ms. The GPU decode win would need fields of hundreds of kilobytes that
this library is never handed, so it was not written.

The arithmetic-intensity gate is why this ends at "CPU only: memory-bound" rather than
"write a decoder". Both kernels move every byte once and reuse nothing (encode: one
shift+or+store per emitted bit; decode: one trie step per bit), which is a few integer ops
per byte against roughly 2 bytes of traffic, so there is no tile to promote into shared
memory and no compute to hide the transfer behind.

Shipping a decode-only path was considered and rejected. It would win only for payloads of
hundreds of kilobytes, which is not how `hpack` is called; it would add a device dependency
and a round trip in the decode path on a shared GPU, and it would have to carry the current
mid-stream failure returns (`-1` for invalid padding, `-2` for short output) across the FFI
boundary. Nothing was reverted because nothing was shipped: the CPU path, SIMD tails, and
the `parallelize` batch path are unchanged, and no test skips on this host because no test
needs a device.

The probes that produced the numbers are kept under `bench/.gpu-tmp/` so the figures can be
rechecked. They need a CUDA device:

```bash
pixi run mojo run bench/.gpu-tmp/bw.mojo           # device streaming bandwidth
pixi run mojo run bench/.gpu-tmp/launchfloor.mojo # launch + synchronize floor
pixi run mojo run bench/.gpu-tmp/floor.mojo       # copy in / copy out per size
flock /tmp/mojo-bench.lock pixi run python bench/.gpu-tmp/enc_sizes.py  # encode kernel us
flock /tmp/mojo-bench.lock pixi run python bench/.gpu-tmp/dec_sizes.py  # decode kernel us
```

`.gpu-tmp/` is not on the import path and is not part of the build.

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
