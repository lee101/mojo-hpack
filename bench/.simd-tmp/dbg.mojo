from std.sys import simd_width_of

comptime BPtr = Pointer[UInt8, AnyOrigin[mut=True]]


@export("d_size8")
def d_size8(addr: Int, idx_addr: Int) -> UInt64:
    var p = BPtr(unsafe_from_address=addr)
    var i = Pointer[UInt8, AnyOrigin[mut=True]](unsafe_from_address=idx_addr)
    var symbols = i.unsafe_load[width=4](0)
    var g = p.unsafe_gather(symbols)
    return g.cast[DType.uint64]().reduce_add()


@export("d_size8b")
def d_size8b(addr: Int, idx_addr: Int) -> UInt64:
    var p = BPtr(unsafe_from_address=addr)
    var i = Pointer[UInt8, AnyOrigin[mut=True]](unsafe_from_address=idx_addr)
    var symbols = i.unsafe_load[width=4](0)
    var g = p.unsafe_gather(symbols)
    return UInt64(g[0]) + UInt64(g[1]) + UInt64(g[2]) + UInt64(g[3])
