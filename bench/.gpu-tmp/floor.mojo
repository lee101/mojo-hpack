from max.gpu import block_idx, thread_idx
from max.gpu.host import DeviceContext
from std.time import perf_counter_ns

comptime BS = 256
comptime FPtr = Pointer[Float64, AnyOrigin[mut=True]]

def scale_kernel(dst: FPtr, src: FPtr, n_value: Int64):
    var n = Int(n_value)
    var i = Int(block_idx.x) * BS + Int(thread_idx.x)
    if i < n:
        dst[i] = src[i] * 2.0

def main() raises:
    var ctx = DeviceContext()
    var n = 16
    var small = ctx.enqueue_create_buffer[DType.float64](n)
    var host = List[Float64](length=n, fill=1.0)
    ctx.enqueue_copy(small, host)
    ctx.synchronize()
    # empty-launch floor
    var best = Int(1 << 62)
    for _ in range(50):
        var t0 = Int(perf_counter_ns())
        ctx.enqueue_function[scale_kernel](small, small, Int64(n), grid_dim=1, block_dim=BS)
        ctx.synchronize()
        var t1 = Int(perf_counter_ns())
        if t1 - t0 < best: best = t1 - t0
    print("empty kernel + sync floor:", Float64(best) / 1e3, "us")

    # smallest useful transfer: 15 B and 60 KB round trip
    for nb in [15, 4096, 61440, 1048576]:
        var cnt = (nb + 7) // 8
        var dbuf = ctx.enqueue_create_buffer[DType.float64](cnt)
        var h = List[Float64](length=cnt, fill=1.0)
        var bh = Int(1 << 62)
        var bd = Int(1 << 62)
        for _ in range(30):
            var t0 = Int(perf_counter_ns())
            ctx.enqueue_copy(dbuf, h)
            ctx.synchronize()
            var t1 = Int(perf_counter_ns())
            ctx.enqueue_copy(h, dbuf)
            ctx.synchronize()
            var t2 = Int(perf_counter_ns())
            if t1 - t0 < bh: bh = t1 - t0
            if t2 - t1 < bd: bd = t2 - t1
        print(nb, "B  H2D", Float64(bh) / 1e3, "us  D2H", Float64(bd) / 1e3, "us  roundtrip",
              Float64(bh + bd) / 1e3, "us")
