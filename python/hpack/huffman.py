"""HPACK Huffman encoder with a Mojo fast path for the RFC codebook."""

from ._lib import huffman_encode
from .huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH


class HuffmanEncoder:
    def __init__(self, huffman_code_list, huffman_code_list_lengths):
        self.huffman_code_list = huffman_code_list
        self.huffman_code_list_lengths = huffman_code_list_lengths
        self._standard = (
            huffman_code_list == REQUEST_CODES
            and huffman_code_list_lengths == REQUEST_CODES_LENGTH
        )

    def encode(self, bytes_to_encode):
        if not bytes_to_encode:
            return b""
        data = bytes(bytes_to_encode)
        if self._standard:
            return huffman_encode(data)
        value = 0
        width = 0
        for byte in data:
            bits = self.huffman_code_list_lengths[byte]
            value = (value << bits) | self.huffman_code_list[byte]
            width += bits
        padding = (-width) % 8
        value = (value << padding) | ((1 << padding) - 1)
        return value.to_bytes((width + padding) // 8, "big")
