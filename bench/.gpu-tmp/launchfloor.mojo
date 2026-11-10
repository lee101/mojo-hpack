from max.gpu import block_idx, thread_idx
from max.gpu.host import DeviceContext
from std.time import perf_counter_ns

comptime BS = 256
comptime FPtr = Pointer[Float64, AnyOrigin[mut=True]]

def noop_kernel(dst: FPtr):
    var i = Int(block_idx.x) * BS + Int(thread_idx.x)
    if i == 100000000:
        dst.store(0, 1.0)

def main() raises:
    var ctx = DeviceContext()
    var buf = ctx.enqueue_create_buffer[DType.float64](256)
    # warm the runtime
    for _ in range(20):
        ctx.enqueue_function[noop_kernel](buf, grid_dim=1, block_dim=BS)
        ctx.synchronize()
    var best = Int(1 << 62)
    var total = 0
    for _ in range(200):
        var t0 = Int(perf_counter_ns())
        ctx.enqueue_function[noop_kernel](buf, grid_dim=1, block_dim=BS)
        ctx.synchronize()
        var t1 = Int(perf_counter_ns())
        if t1 - t0 < best: best = t1 - t0
        total += t1 - t0
    print("launch+sync floor: best", Float64(best) / 1e3, "us  mean", Float64(total) / 200 / 1e3, "us")
