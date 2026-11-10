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
    print("name:", ctx.name())
    for mb in [1, 4, 16, 64, 256]:
        var nbytes = mb * 1024 * 1024
        var n = nbytes // 8
        var n2 = n - 1
        var src_buf = ctx.enqueue_create_buffer[DType.float64](n)
        var dst_buf = ctx.enqueue_create_buffer[DType.float64](n)
        var host = List[Float64](length=n, fill=1.0)
        var grid = (n + BS - 1) // BS
        var best_h2d = Int(1 << 62)
        var best_gpu = Int(1 << 62)
        var best_d2h = Int(1 << 62)
        for _ in range(10):
            var t0 = Int(perf_counter_ns())
            ctx.enqueue_copy(src_buf, host)
            ctx.synchronize()
            var t1 = Int(perf_counter_ns())
            ctx.enqueue_function[scale_kernel](
                dst_buf, src_buf, Int64(n), grid_dim=grid, block_dim=BS)
            ctx.synchronize()
            var t2 = Int(perf_counter_ns())
            ctx.enqueue_copy(host, dst_buf)
            ctx.synchronize()
            var t3 = Int(perf_counter_ns())
            if t1 - t0 < best_h2d: best_h2d = t1 - t0
            if t2 - t1 < best_gpu: best_gpu = t2 - t1
            if t3 - t2 < best_d2h: best_d2h = t3 - t2
        var gb = Float64(nbytes) / 1e9
        print(mb, "MiB  H2D", Float64(best_h2d) / 1e6, "ms", gb / (Float64(best_h2d) / 1e9),
              "GB/s | kernel", Float64(best_gpu) / 1e6, "ms", (gb * 2.0) / (Float64(best_gpu) / 1e9),
              "GB/s | D2H", Float64(best_d2h) / 1e6, "ms", gb / (Float64(best_d2h) / 1e9), "GB/s")
        print("   check dst[0]=", host[0], " dst[last]=", host[n2])
