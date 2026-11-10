from python.hpack.huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH


def enc(codes: Array[UInt32, 257], lengths: Array[UInt32, 257], symbol: Int) -> String:
    var accumulator = UInt64(0)
    var width = Int(lengths[symbol])
    accumulator = (accumulator << UInt64(width)) | UInt64(codes[symbol])
    var bit_count = width
    var out = String()
    var bytes = List[UInt8]()
    while bit_count >= 8:
        bit_count -= 8
        bytes.append(UInt8((accumulator >> UInt64(bit_count)) & 255))
    if bit_count != 0:
        var padding = 8 - bit_count
        accumulator = (accumulator << UInt64(padding)) | ((UInt64(1) << UInt64(padding)) - 1)
        bytes.append(UInt8(accumulator))
    for b in bytes:
        out += String(String(Int(b)) + " ")
    return out


def main():
    var codes = Array[UInt32, 257](fill=UInt32(0))
    var lengths = Array[UInt32, 257](fill=UInt32(0))
    for i in range(257):
        codes[i] = UInt32(REQUEST_CODES[i])
        lengths[i] = UInt32(REQUEST_CODES_LENGTH[i])
    print("w", REQUEST_CODES[119], REQUEST_CODES_LENGTH[119], enc(codes, lengths, 119))
