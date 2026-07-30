"""HPACK Huffman kernels exposed through a small C ABI."""

from std.algorithm import parallelize
from std.sys.info import simd_width_of

comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
comptime U32Ptr = UnsafePointer[UInt32, AnyOrigin[mut=True]]
comptime I32Ptr = UnsafePointer[Int32, AnyOrigin[mut=True]]
comptime I64Ptr = UnsafePointer[Int64, AnyOrigin[mut=True]]


def _encoded_size(src: BPtr, n: Int, lengths: BPtr) -> Int:
    comptime W = simd_width_of[DType.float64]()
    var bits = UInt64(0)
    var i = 0
    while i + W <= n:
        var symbols = src.load[width=W](i)
        var widths = lengths.gather(symbols)
        bits += widths.cast[DType.uint64]().reduce_add()
        i += W
    while i < n:
        bits += UInt64(lengths[Int(src[i])])
        i += 1
    return Int((bits + 7) // 8)


def _encode_to(
    src: BPtr, n: Int, codes: U32Ptr, lengths: BPtr, dst: BPtr
) -> Int:
    var accumulator = UInt64(0)
    var bit_count = 0
    var dst_index = 0

    for i in range(n):
        var symbol = Int(src[i])
        var width = Int(lengths[symbol])
        accumulator = (accumulator << UInt64(width)) | UInt64(codes[symbol])
        bit_count += width
        while bit_count >= 8:
            bit_count -= 8
            dst[dst_index] = UInt8((accumulator >> UInt64(bit_count)) & 255)
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
        dst[dst_index] = UInt8(accumulator)
        dst_index += 1
    return dst_index


@export("mh_huffman_encoded_size")
def mh_huffman_encoded_size(src_addr: Int, n: Int, lengths_addr: Int) abi("C") -> Int:
    if n < 0 or lengths_addr == 0 or (n != 0 and src_addr == 0):
        return -3
    if n == 0:
        return 0
    var src = BPtr(unsafe_from_address=src_addr)
    var lengths = BPtr(unsafe_from_address=lengths_addr)
    return _encoded_size(src, n, lengths)


@export("mh_huffman_encode")
def mh_huffman_encode(
    src_addr: Int, n: Int, codes_addr: Int, lengths_addr: Int, dst_addr: Int
) abi("C") -> Int:
    if (
        n < 0
        or codes_addr == 0
        or lengths_addr == 0
        or (n != 0 and (src_addr == 0 or dst_addr == 0))
    ):
        return -3
    if n == 0:
        return 0
    var src = BPtr(unsafe_from_address=src_addr)
    var codes = U32Ptr(unsafe_from_address=codes_addr)
    var lengths = BPtr(unsafe_from_address=lengths_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    return _encode_to(src, n, codes, lengths, dst)


@export("mh_huffman_encode_batch")
def mh_huffman_encode_batch(
    src_addr: Int,
    source_offsets_addr: Int,
    count: Int,
    codes_addr: Int,
    lengths_addr: Int,
    dst_addr: Int,
    dst_capacity: Int,
    result_offsets_addr: Int,
    use_parallel: Int,
) abi("C") -> Int:
    if (
        count < 0
        or dst_capacity < 0
        or source_offsets_addr == 0
        or codes_addr == 0
        or lengths_addr == 0
        or result_offsets_addr == 0
    ):
        return -3
    var source_offsets = I64Ptr(unsafe_from_address=source_offsets_addr)
    if source_offsets[0] != 0:
        return -3
    for index in range(count):
        if source_offsets[index + 1] < source_offsets[index]:
            return -3
    var source_size = Int(source_offsets[count])
    if source_size != 0 and src_addr == 0:
        return -3
    if count == 0:
        var empty_results = I64Ptr(unsafe_from_address=result_offsets_addr)
        empty_results[0] = 0
        return 0
    var src = BPtr(unsafe_from_address=src_addr)
    var codes = U32Ptr(unsafe_from_address=codes_addr)
    var lengths = BPtr(unsafe_from_address=lengths_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var result_offsets = I64Ptr(unsafe_from_address=result_offsets_addr)

    result_offsets[0] = 0
    for index in range(count):
        var start = Int(source_offsets[index])
        var n = Int(source_offsets[index + 1]) - start
        result_offsets[index + 1] = Int64(_encoded_size(src + start, n, lengths))
    for index in range(count):
        result_offsets[index + 1] += result_offsets[index]

    var total = Int(result_offsets[count])
    if total > dst_capacity:
        return -1
    if total != 0 and dst_addr == 0:
        return -3

    @parameter
    def encode_range(chunk: Int):
        comptime chunk_size = 64
        var first = chunk * chunk_size
        var end = min(first + chunk_size, count)
        for index in range(first, end):
            var source_start = Int(source_offsets[index])
            var source_size = Int(source_offsets[index + 1]) - source_start
            var destination_start = Int(result_offsets[index])
            _ = _encode_to(
                src + source_start,
                source_size,
                codes,
                lengths,
                dst + destination_start,
            )

    if use_parallel != 0 and count >= 256 and Int(source_offsets[count]) >= 65536:
        parallelize[encode_range]((count + 63) // 64)
    else:
        encode_range(0)
        for chunk in range(1, (count + 63) // 64):
            encode_range(chunk)
    return total


@export("mh_huffman_decode")
def mh_huffman_decode(
    src_addr: Int,
    n: Int,
    left_addr: Int,
    right_addr: Int,
    symbols_addr: Int,
    dst_addr: Int,
    dst_capacity: Int,
) abi("C") -> Int:
    if (
        n < 0
        or dst_capacity < 0
        or (n != 0 and (
            src_addr == 0
            or left_addr == 0
            or right_addr == 0
            or symbols_addr == 0
        ))
        or (dst_capacity != 0 and dst_addr == 0)
    ):
        return -3
    if n == 0:
        return 0
    var src = BPtr(unsafe_from_address=src_addr)
    var left = I32Ptr(unsafe_from_address=left_addr)
    var right = I32Ptr(unsafe_from_address=right_addr)
    var symbols = I32Ptr(unsafe_from_address=symbols_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var node = 0
    var dst_index = 0
    var trailing_bits = 0
    var trailing_ones = True

    for i in range(n):
        var byte = Int(src[i])
        for shift in range(7, -1, -1):
            var bit = (byte >> shift) & 1
            trailing_bits += 1
            if bit == 0:
                trailing_ones = False
                node = Int(left[node])
            else:
                node = Int(right[node])
            if node < 0:
                return -1
            var symbol = Int(symbols[node])
            if symbol >= 0:
                if symbol == 256:
                    return -1
                if dst_index >= dst_capacity:
                    return -2
                dst[dst_index] = UInt8(symbol)
                dst_index += 1
                node = 0
                trailing_bits = 0
                trailing_ones = True

    if node != 0 and (trailing_bits > 7 or not trailing_ones):
        return -1
    return dst_index
