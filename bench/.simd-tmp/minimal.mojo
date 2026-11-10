from std.sys import simd_width_of

comptime BPtr = Pointer[UInt8, AnyOrigin[mut=True]]


def _encoded_size_old(src: BPtr, n: Int, lengths: BPtr) -> UInt64:
    comptime W = simd_width_of[DType.float64]()
    var bits = UInt64(0)
    var i = 0
    while i + W <= n:
        var symbols = src.unsafe_load[width=W](i)
        var widths = lengths.unsafe_gather(symbols)
        bits += widths.cast[DType.uint64]().reduce_add()
        i += W
    while i < n:
        bits += UInt64(lengths[unsafe_offset=Int(src[unsafe_offset=i])])
        i += 1
    return bits


def main():
    var lens = Array[UInt8, 256](fill=UInt8(0))
    for i in range(256):
        lens[i] = UInt8(i % 9)
    var lengths = BPtr(unsafe_from_address=Int(lens.unsafe_ptr()))
    var data = Array[UInt8, 8](fill=UInt8(1))
    data[0] = 1
    data[1] = 2
    data[2] = 3
    var src = BPtr(unsafe_from_address=Int(data.unsafe_ptr()))
    print("n=1", _encoded_size_old(src, 1, lengths))
    print("n=3", _encoded_size_old(src, 3, lengths))
    print("n=8", _encoded_size_old(src, 8, lengths))
