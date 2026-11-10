from std.sys import simd_width_of


def main():
    comptime W8 = simd_width_of[DType.uint8]()
    comptime Ptr8 = Pointer[UInt8, AnyOrigin[mut=True]]
    comptime Ptr64 = Pointer[UInt64, AnyOrigin[mut=True]]
    var buf: Array[UInt8, 8] = [0xAB, 0xAB, 0xAB, 0xAB, 0, 0, 0, 0]
    var p = Ptr8(unsafe_from_address=Int(buf.unsafe_ptr()))
    var v = p.unsafe_load[width=W8](0)
    print("W8", W8, "or-shift", v | (v << 1))
    var splat = v.eq(SIMD[DType.uint8, W8](fill=UInt8(0)))
    print("bool splat", splat)
    var both = v.eq(SIMD[DType.uint8, W8](fill=UInt8(0))) | v.eq(SIMD[DType.uint8, W8](fill=UInt8(0xAB)))
    print("bool or", both)

    var q = Ptr64(unsafe_from_address=Int(p))
    var w = q.unsafe_load[width=4](0)
    var acc = SIMD[DType.uint64, 4](0)
    acc |= w << 1
    print("acc", acc, ((acc >> 4) & 0xff).cast[DType.uint8]())

    var bits = SIMD[DType.int64, 4](0)
    bits += 5
    print("int64 simd", bits * 3, bits.cast[DType.uint64]().reduce_add())

    var lhs = SIMD[DType.int64, 4](1, 2, 3, 4)
    var rhs = SIMD[DType.int64, 4](2, 2, 2, 2)
    print("lt", lhs.lt(rhs), "gt", lhs.gt(rhs))
    var idx = SIMD[DType.uint64, 4](0x10, 0x11, 0x12, 0x13)
    print("idx", idx & 15, idx >> 4)
    var m = idx.lt(SIMD[DType.uint64, 4](0x12))
    print("idx lt", m)
    print("reduce", v.reduce_add(), v.cast[DType.int32]().reduce_add())
