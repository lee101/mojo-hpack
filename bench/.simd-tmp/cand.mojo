"""Scratch candidate kernels, exported under short names."""
comptime BPtr = Pointer[UInt8, AnyOrigin[mut=True]]
comptime U32Ptr = Pointer[UInt32, AnyOrigin[mut=True]]


def _encode_mask(
    src: BPtr, n: Int, codes: U32Ptr, lengths: BPtr, dst: BPtr
) -> Int:
    var accumulator = UInt64(0)
    var bit_count = 0
    var dst_index = 0
    for i in range(n):
        var symbol = Int(src[unsafe_offset=i])
        var width = Int(lengths[unsafe_offset=symbol])
        accumulator = (accumulator << UInt64(width)) | UInt64(
            codes[unsafe_offset=symbol]
        )
        bit_count += width
        while bit_count >= 8:
            bit_count -= 8
            dst[unsafe_offset=dst_index] = UInt8(
                (accumulator >> UInt64(bit_count)) & 255
            )
            dst_index += 1
        if bit_count == 0:
            accumulator = 0
        else:
            accumulator &= (UInt64(1) << UInt64(bit_count)) - 1
    if bit_count != 0:
        var padding = 8 - bit_count
        accumulator = (accumulator << UInt64(padding)) | (
            (UInt64(1) << UInt64(padding)) - 1
        )
        dst[unsafe_offset=dst_index] = UInt8(accumulator)
        dst_index += 1
    return dst_index


@export("k1_encode")
def k1_encode(
    src_addr: Int, n: Int, codes_addr: Int, lengths_addr: Int, dst_addr: Int
) abi("C") -> Int:
    return _encode_mask(
        BPtr(unsafe_from_address=src_addr), n,
        U32Ptr(unsafe_from_address=codes_addr), BPtr(unsafe_from_address=lengths_addr),
        BPtr(unsafe_from_address=dst_addr),
    )


@export("k_debug")
def k_debug(src_addr: Int, n: Int, codes_addr: Int, lengths_addr: Int, dst_addr: Int) abi("C") -> Int:
    var src = BPtr(unsafe_from_address=src_addr)
    var codes = U32Ptr(unsafe_from_address=codes_addr)
    var lengths = BPtr(unsafe_from_address=lengths_addr)
    var symbol = Int(src.unsafe_load(0))
    var width = Int(lengths.unsafe_load(symbol))
    var code = Int(codes.unsafe_load(symbol))
    # return width * 10^6 + code, plus a marker bit
    return (width << 40) | code


@export("k_len8")
def k_len8(addr: Int, idx: Int) -> Int:
    var p = BPtr(unsafe_from_address=addr)
    return Int(p.unsafe_load(idx))


@export("k_len32")
def k_len32(addr: Int, idx: Int) -> Int:
    var p = U32Ptr(unsafe_from_address=addr)
    return Int(p.unsafe_load(idx))


@export("k_len_stride")
def k_len_stride(addr: Int, idx: Int) -> Int:
    var q = UInt64(addr)
    q += UInt64(idx)
    var p = BPtr(unsafe_from_address=Int(q))
    return Int(p.unsafe_load(0))


@export("k_args")
def k_args(a: Int, b: Int, c: Int, d: Int, e: Int) abi("C") -> Int:
    return (a & 0xff) + (b & 0xff) * 256 + (c & 0xff) * 65536 + (d & 0xff) * 16777216 + (e & 0xff) * 1099511627776
