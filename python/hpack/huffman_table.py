"""HPACK Huffman decoder backed by Mojo."""

from ._lib import huffman_decode


def decode_huffman(huffman_string):
    if not huffman_string:
        return b""
    return huffman_decode(bytes(huffman_string))
