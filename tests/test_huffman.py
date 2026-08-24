import os
import random

import pytest

from hpack import HPACKDecodingError
from hpack._lib import PARALLEL_MIN_BYTES, huffman_encode_many
from hpack._lib import huffman_decode, huffman_encode, lib
from hpack.huffman import HuffmanEncoder
from hpack.huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH
from hpack.huffman_table import decode_huffman


RFC_VECTORS = (
    (b"www.example.com", "f1e3c2e5f23a6ba0ab90f4ff"),
    (b"no-cache", "a8eb10649cbf"),
    (b"custom-key", "25a849e95ba97d7f"),
    (b"custom-value", "25a849e95bb8e8b4bf"),
)


def test_rfc_7541_huffman_vectors():
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    for plain, encoded in RFC_VECTORS:
        assert coder.encode(plain).hex() == encoded
        assert decode_huffman(bytes.fromhex(encoded)) == plain


def test_custom_codebook_uses_compatible_fallback(upstream_hpack):
    from _upstream_hpack.huffman import HuffmanEncoder as UpstreamEncoder

    codes = [index for index in range(256)]
    lengths = [8] * 256
    plain = bytes(range(256))
    assert HuffmanEncoder(codes, lengths).encode(plain) == UpstreamEncoder(
        codes, lengths
    ).encode(plain)


def test_empty_huffman_string():
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    assert coder.encode(b"") == b""
    assert coder.encode(None) == b""
    assert decode_huffman(b"") == b""


def test_all_octets_round_trip():
    plain = bytes(range(256)) * 8
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    assert decode_huffman(coder.encode(plain)) == plain


def test_random_binary_matches_upstream(upstream_hpack):
    from _upstream_hpack.huffman import HuffmanEncoder as UpstreamEncoder
    from _upstream_hpack.huffman_constants import REQUEST_CODES as UP_CODES
    from _upstream_hpack.huffman_constants import REQUEST_CODES_LENGTH as UP_LENGTHS

    ours = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    theirs = UpstreamEncoder(UP_CODES, UP_LENGTHS)
    rng = random.Random(19)
    for length in (1, 2, 3, 7, 31, 128, 1024, 65_537):
        plain = rng.randbytes(length)
        assert ours.encode(plain) == theirs.encode(plain)
        assert decode_huffman(ours.encode(plain)) == plain


@pytest.mark.parametrize("length", [32, 33])
def test_huffman_encode_python_threshold(upstream_hpack, length):
    from _upstream_hpack.huffman import HuffmanEncoder as UpstreamEncoder
    from _upstream_hpack.huffman_constants import REQUEST_CODES as UP_CODES
    from _upstream_hpack.huffman_constants import REQUEST_CODES_LENGTH as UP_LENGTHS

    plain = bytes(range(length))
    assert HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH).encode(plain) == (
        UpstreamEncoder(UP_CODES, UP_LENGTHS).encode(plain)
    )


@pytest.mark.parametrize("plain_length,encoded_length", [(51, 32), (52, 33)])
def test_huffman_decode_python_threshold(plain_length, encoded_length):
    plain = b"a" * plain_length
    encoded = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH).encode(plain)
    assert len(encoded) == encoded_length
    assert decode_huffman(encoded) == plain


def test_batched_huffman_simd_tails():
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    values = [
        bytes(range(length))
        for length in (0, 1, 2, 3, 5, 7, 9, 15, 17, 31)
    ]
    assert huffman_encode_many(values) == [coder.encode(value) for value in values]


@pytest.mark.parametrize("size", [PARALLEL_MIN_BYTES - 1, PARALLEL_MIN_BYTES])
def test_batched_huffman_parallel_threshold(size):
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    count = 256
    width, remainder = divmod(size, count)
    values = [bytes([index & 0xFF]) * (width + (index < remainder)) for index in range(count)]
    assert huffman_encode_many(values) == [coder.encode(value) for value in values]


def test_memoryview_decode():
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    encoded = coder.encode(b"memoryview")
    assert decode_huffman(memoryview(encoded)) == b"memoryview"


@pytest.mark.parametrize("encoded", [b"\xff", b"\x00", b"\xff\xff\xff\xff"])
def test_invalid_huffman_rejected(encoded):
    with pytest.raises(HPACKDecodingError):
        decode_huffman(encoded)


def test_large_ascii_round_trip():
    plain = (b"content-type: application/json; charset=utf-8\r\n" * 30_000)
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    encoded = coder.encode(plain)
    assert len(encoded) < len(plain)
    assert decode_huffman(encoded) == plain


def test_random_os_bytes_round_trip():
    plain = os.urandom(10_003)
    coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
    assert decode_huffman(coder.encode(plain)) == plain


@pytest.mark.parametrize(
    "function,value",
    [
        (huffman_encode, bytearray(b"x")),
        (huffman_decode, memoryview(b"x")),
        (huffman_encode_many, (b"x",)),
        (huffman_encode_many, [bytearray(b"x")]),
    ],
)
def test_ffi_wrappers_reject_ambiguous_buffer_types(function, value):
    with pytest.raises(TypeError):
        function(value)


def test_exported_kernels_reject_invalid_addresses_and_lengths():
    mojo = lib()
    assert mojo.mh_huffman_encoded_size(0, 1, 0) == -3
    assert mojo.mh_huffman_encode(0, -1, 0, 0, 0) == -3
    assert mojo.mh_huffman_decode(0, 1, 0, 0, 0, 0, 0) == -3


def test_empty_batch_has_stable_zero_offset():
    assert huffman_encode_many([b"", b""]) == [b"", b""]
