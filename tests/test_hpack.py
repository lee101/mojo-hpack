import random

import pytest

import hpack
from hpack import (
    Decoder,
    Encoder,
    HPACKDecodingError,
    HeaderTuple,
    InvalidTableIndexError,
    InvalidTableSizeError,
    NeverIndexedHeaderTuple,
    OversizedHeaderListError,
)
from hpack.hpack import decode_integer, encode_integer
from hpack.table import HeaderTable, table_entry_size


REQUESTS = (
    (
        [(b":method", b"GET"), (b":scheme", b"http"), (b":path", b"/"),
         (b":authority", b"www.example.com")],
        "828684418cf1e3c2e5f23a6ba0ab90f4ff",
    ),
    (
        [(b":method", b"GET"), (b":scheme", b"http"), (b":path", b"/"),
         (b":authority", b"www.example.com"), (b"cache-control", b"no-cache")],
        "828684be5886a8eb10649cbf",
    ),
    (
        [(b":method", b"GET"), (b":scheme", b"https"), (b":path", b"/index.html"),
         (b":authority", b"www.example.com"), (b"custom-key", b"custom-value")],
        "828785bf408825a849e95ba97d7f8925a849e95bb8e8b4bf",
    ),
)


def test_rfc_7541_request_examples_statefully():
    encoder = Encoder()
    decoder = Decoder()
    for headers, encoded in REQUESTS:
        block = encoder.encode(headers, huffman=True)
        assert block.hex() == encoded
        assert decoder.decode(block, raw=True) == headers


def test_full_encoder_exact_parity_across_state(upstream_hpack):
    ours = Encoder()
    theirs = upstream_hpack.Encoder()
    rng = random.Random(7)
    common = [
        (b":method", b"GET"), (b":scheme", b"https"), (b":path", b"/resource"),
        (b":authority", b"example.test"), (b"accept", b"application/json"),
    ]
    for index in range(200):
        random_value = rng.randbytes(rng.randrange(0, 80))
        headers = common + [(f"x-test-{index % 11}".encode(), random_value)]
        assert ours.encode(headers) == theirs.encode(headers)


@pytest.mark.parametrize("count", [127, 128])
def test_large_encoder_batch_threshold_parity(upstream_hpack, count):
    headers = [
        (
            f"x-tail-{index}".encode(),
            bytes((index + offset) & 0xFF for offset in range(129)),
        )
        for index in range(count)
    ]
    assert Encoder().encode(headers) == upstream_hpack.Encoder().encode(headers)


def test_full_decoder_reads_upstream_state(upstream_hpack):
    upstream_encoder = upstream_hpack.Encoder()
    decoder = Decoder()
    blocks = [
        [(b":status", b"200"), (b"content-type", b"text/plain"), (b"x-seq", str(i).encode())]
        for i in range(100)
    ]
    for headers in blocks:
        encoded = upstream_encoder.encode(headers)
        assert decoder.decode(encoded, raw=True) == headers


def test_non_huffman_encoding_parity(upstream_hpack):
    headers = [(b"custom-key", b"a value with spaces"), (b"x-empty", b"")]
    assert Encoder().encode(headers, huffman=False) == upstream_hpack.Encoder().encode(
        headers, huffman=False
    )


def test_dict_pseudo_headers_are_first():
    decoded = Decoder().decode(
        Encoder().encode({"regular": "value", ":path": "/", ":method": "GET"})
    )
    assert decoded == [(":path", "/"), (":method", "GET"), ("regular", "value")]


def test_sensitive_header_is_never_indexed():
    header = NeverIndexedHeaderTuple(b"authorization", b"secret")
    block = Encoder().encode([header])
    assert block[0] & 0x10
    decoded = Decoder().decode(block, raw=True)
    assert decoded == [header]
    assert isinstance(decoded[0], NeverIndexedHeaderTuple)


def test_three_tuple_sensitive_form():
    block = Encoder().encode([(b"authorization", b"secret", True)])
    decoded = Decoder().decode(block, raw=True)
    assert isinstance(decoded[0], NeverIndexedHeaderTuple)


def test_raw_and_unicode_modes():
    block = Encoder().encode([("x-name", "café")])
    assert Decoder().decode(block) == [("x-name", "café")]
    assert Decoder().decode(block, raw=True) == [(b"x-name", "café".encode())]


def test_integer_codec_rfc_examples():
    encoded = encode_integer(1337, 5)
    assert bytes(encoded) == bytes.fromhex("1f9a0a")
    assert decode_integer(bytes.fromhex("1f9a0a"), 5) == (1337, 3)


def test_integer_codec_matches_upstream(upstream_hpack):
    from _upstream_hpack.hpack import decode_integer as upstream_decode
    from _upstream_hpack.hpack import encode_integer as upstream_encode

    for prefix in range(1, 9):
        for value in (0, 1, (1 << prefix) - 2, (1 << prefix) - 1, 127, 128, 255, 4096, 2**32 - 1):
            encoded = encode_integer(value, prefix)
            assert encoded == upstream_encode(value, prefix)
            assert decode_integer(encoded, prefix) == upstream_decode(encoded, prefix)


@pytest.mark.parametrize("value,prefix", [(-1, 5), (1, 0), (1, 9)])
def test_integer_codec_validation(value, prefix):
    with pytest.raises(ValueError):
        encode_integer(value, prefix)


def test_truncated_integer_rejected():
    with pytest.raises(HPACKDecodingError):
        decode_integer(b"\x1f\x80", 5)


def test_dynamic_table_resize_parity(upstream_hpack):
    ours = Encoder()
    theirs = upstream_hpack.Encoder()
    for size in (512, 128, 1024):
        ours.header_table_size = size
        theirs.header_table_size = size
    headers = [(b"x-table", b"value")]
    block = ours.encode(headers)
    assert block == theirs.encode(headers)
    decoder = Decoder()
    decoder.max_allowed_table_size = 1024
    assert decoder.decode(block, raw=True) == headers


def test_oversized_header_list_rejected():
    block = Encoder().encode([(b"x-large", b"a" * 100)])
    with pytest.raises(OversizedHeaderListError):
        Decoder(max_header_list_size=50).decode(block)


def test_invalid_table_size_rejected():
    encoder = Encoder()
    encoder.header_table_size = 4097
    with pytest.raises(InvalidTableSizeError):
        Decoder().decode(encoder.encode([]))


def test_table_size_update_after_header_rejected():
    block = Encoder().encode([(b"x", b"y")], huffman=False) + b"\x20"
    with pytest.raises(HPACKDecodingError):
        Decoder().decode(block)


def test_invalid_static_table_index():
    with pytest.raises(InvalidTableIndexError):
        HeaderTable().get_by_index(0)
    with pytest.raises(InvalidTableIndexError):
        Decoder().decode(b"\xff\x00")


def test_header_table_eviction_and_size():
    table = HeaderTable()
    table.maxsize = table_entry_size(b"a", b"1") + table_entry_size(b"b", b"2")
    table.add(b"a", b"1")
    table.add(b"b", b"2")
    table.add(b"c", b"3")
    assert list(table.dynamic_entries) == [(b"c", b"3"), (b"b", b"2")]


def test_public_surface_matches_upstream(upstream_hpack):
    assert hpack.__all__ == upstream_hpack.__all__
    assert HeaderTuple(b"a", b"b").indexable
    assert not NeverIndexedHeaderTuple(b"a", b"b").indexable
