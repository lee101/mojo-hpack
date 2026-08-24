"""HPACK Huffman decoder backed by Mojo."""

from .exceptions import HPACKDecodingError
from ._lib import huffman_decode
from .huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH


PYTHON_DECODE_THRESHOLD = 32


def _build_byte_decoder():
    children = [[-1, -1]]
    symbols = [-1]
    depths = [0]
    all_ones = [True]
    for symbol, (code, width) in enumerate(zip(REQUEST_CODES, REQUEST_CODES_LENGTH)):
        node = 0
        for shift in range(width - 1, -1, -1):
            bit = (code >> shift) & 1
            child = children[node][bit]
            if child < 0:
                child = len(children)
                children[node][bit] = child
                children.append([-1, -1])
                symbols.append(-1)
                depths.append(depths[node] + 1)
                all_ones.append(all_ones[node] and bit == 1)
            node = child
        symbols[node] = symbol

    row_nodes = [0]
    node_rows = {0: 0}
    rows = []
    outputs = {b"": b""}
    for state_node in row_nodes:
        row = []
        for value in range(256):
            node = state_node
            emitted = bytearray()
            for shift in range(7, -1, -1):
                node = children[node][(value >> shift) & 1]
                if node < 0 or symbols[node] == 256:
                    break
                if symbols[node] >= 0:
                    emitted.append(symbols[node])
                    node = 0
            if node < 0 or (node >= 0 and symbols[node] == 256):
                row.append((-1, b""))
                continue
            if node not in node_rows:
                node_rows[node] = len(row_nodes)
                row_nodes.append(node)
            output = bytes(emitted)
            output = outputs.setdefault(output, output)
            row.append((node_rows[node], output))
        rows.append(tuple(row))
    complete = sum(
        1 << row
        for row, node in enumerate(row_nodes)
        if node == 0 or (depths[node] <= 7 and all_ones[node])
    )
    return tuple(rows), complete


_BYTE_DECODER, _COMPLETE_ROWS = _build_byte_decoder()


def _decode_short(data) -> bytes:
    row = 0
    decoded = bytearray()
    for value in data:
        row, emitted = _BYTE_DECODER[row][value]
        if row < 0:
            raise HPACKDecodingError("Invalid Huffman string")
        if emitted:
            decoded.extend(emitted)
    if not (_COMPLETE_ROWS & (1 << row)):
        raise HPACKDecodingError("Invalid Huffman string")
    return bytes(decoded)


def decode_huffman(huffman_string):
    if not huffman_string:
        return b""
    if len(huffman_string) <= PYTHON_DECODE_THRESHOLD:
        return _decode_short(huffman_string)
    return huffman_decode(bytes(huffman_string))
