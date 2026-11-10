def main():
    var b = SIMD[DType.uint8, 32](0)
    print("pos ok", b)
    var v = SIMD[DType.uint8, 4](1, 2, 3, 4)
    var s = SIMD[DType.uint8, 4](2)
    print(v.lt(s), v.eq(s), v.ge(s))
    var z = SIMD[DType.uint64, 4](0xDEADBEEFCAFEF00D)
    print(z, z >> 8, z & 0xff)
    print("splatcmp", v.eq(SIMD[DType.uint8, 4](1)), v.lt(SIMD[DType.uint8, 4](3)))
