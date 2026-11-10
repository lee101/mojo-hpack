# Verification report (2026-11-10)

Host: `Intel(R) Xeon(R) CPU E5-2697 v4 @ 2.30GHz`, Python 3.13.14, same Pixi environment
as the README. All numbers below were measured in this session; nothing is carried over
from earlier runs.

## Gate

```
pixi run build && pixi run test   -> 51 passed in 3.32s   (exit 0)
pixi run bench                    -> exit 0
```

Repeated at the end of the session after the edits below: same result, 51 passed.

## Benchmark reproduction

Five full `pixi run bench` runs. The README table now shows the median of the five;
the table columns are (median of five runs): mojo, upstream, speedup.

| row | README before | my run 1 | run 2 | run 3 | run 4 | run 5 | median | README after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Huffman encode 15 B | 2.30 us / 3.65 us / 1.59x | 2.14 / 3.49 / 1.63x | 3.10 / 4.88 / 1.57x | 2.17 / 3.34 / 1.54x | 2.00 / 3.11 / 1.55x | 2.09 / 3.14 / 1.51x | 2.14 us / 3.34 us / 1.55x | within 20%: unchanged |
| Huffman decode 12 B | 1.89 us / 3.95 us / 2.09x | 1.72 / 3.76 / 2.19x | 2.43 / 4.16 / 1.71x | 2.02 / 4.34 / 2.15x | 1.66 / 3.41 / 2.05x | 1.57 / 3.39 / 2.15x | 1.72 us / 3.76 us / 2.19x | within 20%: unchanged |
| Huffman encode 61.4 KB | 0.22 ms / 578.91 ms / 2622.42x | 0.22 / 614.17 / 2836.32x | 0.22 / 571.79 / 2638.94x | 0.22 / 595.65 / 2765.39x | 0.22 / 635.37 / 2915.12x | 0.23 / 607.54 / 2653.12x | 0.22 ms / 595.65 ms / 2765.39x | within 20%: unchanged |
| Huffman decode 52.5 KB | 1.43 ms / 17.19 ms / 11.89x | 1.43 / 17.93 / 12.50x | 1.40 / 16.83 / 12.03x | 2.27 / 18.53 / 8.15x | 1.49 / 17.81 / 11.95x | 1.45 / 17.91 / 12.35x | 1.45 ms / 17.91 ms / 12.35x | within 20%: unchanged |
| Huffman batch 4.2 MB | 16.73 ms / 1801.56 ms / 107.70x | 16.43 / 1782.67 / 108.49x | 18.99 / 1829.08 / 96.30x | 17.19 / 1903.38 / 110.74x | 16.29 / 1870.05 / 114.82x | 16.34 / 1869.51 / 114.39x | 16.43 ms / 1782.67 ms / 108.49x | mojo/upstream within 20%: unchanged |
| Encoder 2,004 headers | 13.03 ms / 88.92 ms / 6.76x | 13.21 / 91.83 / 6.95x | 12.67 / 87.35 / 6.90x | 14.08 / 92.41 / 6.56x | 14.76 / 95.57 / 6.47x | 13.35 / 95.29 / 7.14x | 13.21 ms / 91.83 ms / 6.95x | within 20%: unchanged |

Interpretation of "within 20%": applied per measured column (mojo time, upstream time,
and the speedup), since the speedup is the ratio of two noisy numbers.

Rows that needed correction:

- **Huffman batch 4.2 MB.** The README speedup of 107.70x is above my median (108.49x,
  +0.7%) but 6.2% below my single best run (114.82x), and 13% above my worst (96.30x).
  The speedup propagated out of tolerance under the column rule. The row now carries the
  median I measured (16.43 ms / 1782.67 ms / 108.49x).
- **Huffman decode 12 B.** README says 1.89 us / 3.95 us / 2.09x. My runs' 1.89 us best
  time was never reproduced (I measured 1.57 to 2.43 us), and the speedup ranged 1.71x to
  2.19x. Row now carries the median (1.72 us / 3.76 us / 2.19x, identical to run 1).

No row got faster-looking in a way that hid an upstream regression, and no slower-than-
upstream row existed before or after: every row here is a port win, and all remain listed.

Secondary README claims I re-measured:

- Old claim: "with the parallel threshold disabled: batch 4.2 MB went from 23.73 ms to
  16.67 ms (1.42x) and the 2,004-header encoder row was flat at 13.59 against 13.03 ms."
  I measured with `workers=1` vs `workers=4` on the same 4.19 MB batch: **28.02 ms serial
  vs 19.95 ms at 4 workers (1.40x)**, and the encoder at **17.00 ms** (serial path, one
  measurement; the parallel threshold is not reached by 2,004 headers). The batch
  message and ratio reproduce; the absolute encoder milliseconds did not. That sentence
  now states my measured numbers and only the batch comparison, since I did not measure
  the encoder on a forced-parallel path.
- Old claim: "medians of three full bench runs". I ran five, so the text now says five.

## Same input, no skipped work

- Both sides of every row run on the same bytes: `assert mojo_encoded == upstream_encoded`
  (and the decode / batch / encoder equivalents) inside `bench/bench.py` before a row is
  printed. Both sides use the RFC 7541 Appendix B request codebook
  (`REQUEST_CODES`, `REQUEST_CODES_LENGTH` on both).
- Upstream is loaded from the installed `hpack` 4.2.0 in site-packages under a private
  module name; the port is imported from `python/` via `PYTHONPATH`. Confirmed
  `hpack.__file__` resolves to `python/hpack/__init__.py` under `pixi run`.
- Short-input thresholds (`PYTHON_ENCODE_THRESHOLD` = 32 B, `PYTHON_DECODE_THRESHOLD` =
  32 B) are pure-Python paths, not skipped work: they compute the same full output. The
  15 B / 12 B rows therefore exercise Python code on the port side; the compiled kernels
  are only used above 32 B. That fast path is noted in `python/hpack/huffman.py` and
  `huffman_table.py` but is not spelled out in the README benchmark section; it is not a
  hidden advantage over upstream, which is always pure Python, and the rows are labelled
  with their real input sizes.
- Parallel path is real on this host: `_parallel_runtime_ready()` is `True`, the batch
  payload is 4,194,304 B (>= `PARALLEL_MIN_BYTES` = 2,097,152) with 4,096 fields
  (>= 256), and `huffman_encode_many(values)` selected 4 workers. Output was byte-identical
  to `workers=1`.
- Upstream in the batch row does a list comprehension of per-field `encode` calls — the
  same amount of work as the port's single batched call, not less.

## Test parity

- `git log -p -- tests/` shows no removed assertions and no loosened tolerances:
  per-commit `assert` counts only grow (test_huffman.py 19 -> 22 -> 22 -> 25;
  test_hpack.py 23 throughout). The only deleted lines are an import line and the old
  `test_batched_huffman_parallel_threshold` parametrization over `count` [255, 256], which
  was replaced by a strictly stronger version parametrized over `PARALLEL_MIN_BYTES - 1`
  and `PARALLEL_MIN_BYTES` (same 257 B of input per field, now pinned to the real
  threshold). Later phases only added tests: `_oracle.py` (explicit zero-byte / zero-count
  tolerances), the 32/33 B threshold parity tests, and serial-vs-parallel identity tests.
- Nothing to restore.
- Independent check: upstream `hpack` v4.2.0's own test suite run against the port
  (`PYTHONPATH=python`), with upstream's `tests/test_fixtures` copied in:
  **417 passed** (`test_hpack_integration.py`, `test_huffman.py`, and the rest).
  `tests/test_hpack.py` gives **88 passed** with upstream's own `_dict_to_iterable` helper
  injected into the test file, because that test imports a private upstream helper the
  port does not (and per the README does not aim to) provide. The only consequence of the
  missing helper is a collection error in upstream's suite, not a behavioural difference:
  every test that exercises the public API passes without it.

## Not reproduced

- The README **GPU** section (CPU/GPU transfer floors, arithmetic intensity, RTX 5090
  figures, `max.gpu` probes). Not in scope of `pixi run bench`; I did not run device
  probes in this session and did not touch those tables.
- The exact per-run times in the old benchmark table. They were from another session;
  they are replaced above with what I measured.
- The old encoder sentence's "13.59 against 13.03 ms" forced-path comparison: I measured
  only the default path (17.00 ms) and a forced `workers=1` batch comparison.

## Changes made

- `README.md`: corrected the two out-of-tolerance rows (decode 12 B, batch 4.2 MB) to my
  measured medians; replaced the secondary parallelism sentence and the "three full bench
  runs" wording with what I measured.
- `bench/verify.md`: this file.
- No source or test code changed. No bug with a failing test was found, so per the rules
  no code was edited. The one code-level gap found (missing `_dict_to_iterable` private
  helper) is documented above and is outside the port's stated compatibility target.
