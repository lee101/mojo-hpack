"""HPACK header compression compatible with the Python hpack API."""

from .exceptions import HPACKDecodingError, InvalidTableSizeError, OversizedHeaderListError
from ._lib import huffman_encode_many
from .huffman import HuffmanEncoder
from .huffman_constants import REQUEST_CODES, REQUEST_CODES_LENGTH
from .huffman_table import decode_huffman
from .struct import HeaderTuple, NeverIndexedHeaderTuple
from .table import HeaderTable, table_entry_size

INDEX_NONE = b"\x00"
INDEX_NEVER = b"\x10"
INDEX_INCREMENTAL = b"\x40"
VARINT_MAX_LENGTH = 5
DEFAULT_MAX_HEADER_LIST_SIZE = 2**16
HUFFMAN_BATCH_THRESHOLD = 128


def encode_integer(integer: int, prefix_bits: int) -> bytearray:
    if integer < 0:
        raise ValueError(f"Can only encode positive integers, got {integer}")
    if prefix_bits < 1 or prefix_bits > 8:
        raise ValueError(f"Prefix bits must be between 1 and 8, got {prefix_bits}")
    maximum = (1 << prefix_bits) - 1
    if integer < maximum:
        return bytearray([integer])
    result = [maximum]
    integer -= maximum
    while integer >= 128:
        result.append((integer & 127) | 128)
        integer >>= 7
    result.append(integer)
    return bytearray(result)


def decode_integer(data, prefix_bits: int) -> tuple[int, int]:
    if prefix_bits < 1 or prefix_bits > 8:
        raise ValueError(f"Prefix bits must be between 1 and 8, got {prefix_bits}")
    maximum = (1 << prefix_bits) - 1
    index = 1
    shift = 0
    try:
        number = data[0] & maximum
        if number == maximum:
            while True:
                next_byte = data[index]
                index += 1
                number += (next_byte & 127) << shift
                if next_byte < 128:
                    break
                shift += 7
                if index > VARINT_MAX_LENGTH:
                    raise HPACKDecodingError(
                        f"Variable integer representation is too long: {data!r}"
                    )
    except IndexError as error:
        raise HPACKDecodingError(
            f"Unable to decode HPACK integer representation from {data!r}"
        ) from error
    return number, index


def _to_bytes(value):
    if type(value) is bytes:
        return value
    if type(value) is not str:
        value = str(value)
    return value.encode("utf-8")


def _unicode_if_needed(header, raw):
    name, value = bytes(header[0]), bytes(header[1])
    if not raw:
        name, value = name.decode("utf-8"), value.decode("utf-8")
    return header.__class__(name, value)


class Encoder:
    def __init__(self) -> None:
        self.header_table = HeaderTable()
        self.huffman_coder = HuffmanEncoder(REQUEST_CODES, REQUEST_CODES_LENGTH)
        self.table_size_changes = []

    @property
    def header_table_size(self):
        return self.header_table.maxsize

    @header_table_size.setter
    def header_table_size(self, value):
        self.header_table.maxsize = value
        if self.header_table.resized:
            self.table_size_changes.append(value)

    def encode(self, headers, huffman: bool = True) -> bytes:
        if (
            huffman
            and type(headers) in (list, tuple)
            and len(headers) >= HUFFMAN_BATCH_THRESHOLD
        ):
            block = []
            if self.header_table.resized:
                block.append(self._encode_table_size_change())
                self.header_table.resized = False
            prepared = []
            fields = []
            for header in headers:
                if isinstance(header, HeaderTuple):
                    sensitive = not header.indexable
                else:
                    sensitive = header[2] if len(header) > 2 else False
                item = (_to_bytes(header[0]), _to_bytes(header[1]))
                prepared.append((item, sensitive))
                fields.extend(item)
            encoded_fields = huffman_encode_many(fields)
            for index, (item, sensitive) in enumerate(prepared):
                block.append(
                    self.add(
                        item,
                        sensitive,
                        True,
                        _encoded=(
                            encoded_fields[index * 2],
                            encoded_fields[index * 2 + 1],
                        ),
                    )
                )
            return b"".join(block)
        if isinstance(headers, dict):
            keys = sorted(headers, key=lambda key: not _to_bytes(key).startswith(b":"))
            source = ((key, headers[key]) for key in keys)
        else:
            source = iter(headers)
        block = []
        if self.header_table.resized:
            block.append(self._encode_table_size_change())
            self.header_table.resized = False
        for header in source:
            if isinstance(header, HeaderTuple):
                sensitive = not header.indexable
            else:
                sensitive = header[2] if len(header) > 2 else False
            item = (_to_bytes(header[0]), _to_bytes(header[1]))
            block.append(self.add(item, sensitive, huffman))
        return b"".join(block)

    def add(self, to_add, sensitive, huffman=False, *, _encoded=None):
        name, value = to_add
        indexbit = INDEX_NEVER if sensitive else INDEX_INCREMENTAL
        match = self.header_table.search(name, value)
        if match is None:
            encoded = self._encode_literal(
                name, value, indexbit, huffman, _encoded=_encoded
            )
            if not sensitive:
                self.header_table.add(name, value)
            return encoded
        index, matched_name, perfect = match
        if perfect is not None:
            return self._encode_indexed(index)
        encoded = self._encode_indexed_literal(
            index, value, indexbit, huffman, _encoded=_encoded
        )
        if not sensitive:
            self.header_table.add(matched_name, value)
        return encoded

    def _encode_indexed(self, index):
        field = encode_integer(index, 7)
        field[0] |= 0x80
        return bytes(field)

    def _encode_literal(
        self, name, value, indexbit, huffman=False, *, _encoded=None
    ):
        if huffman:
            if _encoded is None:
                name = self.huffman_coder.encode(name)
                value = self.huffman_coder.encode(value)
            else:
                name, value = _encoded
        name_len = encode_integer(len(name), 7)
        value_len = encode_integer(len(value), 7)
        if huffman:
            name_len[0] |= 0x80
            value_len[0] |= 0x80
        return b"".join((indexbit, bytes(name_len), name, bytes(value_len), value))

    def _encode_indexed_literal(
        self, index, value, indexbit, huffman=False, *, _encoded=None
    ):
        prefix = encode_integer(index, 6 if indexbit == INDEX_INCREMENTAL else 4)
        prefix[0] |= indexbit[0]
        if huffman:
            if _encoded is None:
                value = self.huffman_coder.encode(value)
            else:
                value = _encoded[1]
        value_len = encode_integer(len(value), 7)
        if huffman:
            value_len[0] |= 0x80
        return bytes(prefix) + bytes(value_len) + value

    def _encode_table_size_change(self):
        block = bytearray()
        for size in self.table_size_changes:
            encoded = encode_integer(size, 5)
            encoded[0] |= 0x20
            block.extend(encoded)
        self.table_size_changes = []
        return bytes(block)


class Decoder:
    def __init__(self, max_header_list_size: int = DEFAULT_MAX_HEADER_LIST_SIZE) -> None:
        self.header_table = HeaderTable()
        self.max_header_list_size = max_header_list_size
        self.max_allowed_table_size = self.header_table.maxsize

    @property
    def header_table_size(self):
        return self.header_table.maxsize

    @header_table_size.setter
    def header_table_size(self, value):
        self.header_table.maxsize = value

    def decode(self, data: bytes, raw: bool = False):
        data_mem = memoryview(data)
        headers = []
        inflated_size = 0
        current_index = 0
        while current_index < len(data):
            current = data[current_index]
            if current & 0x80:
                header, consumed = self._decode_indexed(data_mem[current_index:])
            elif current & 0x40:
                header, consumed = self._decode_literal_index(data_mem[current_index:])
            elif current & 0x20:
                if headers:
                    raise HPACKDecodingError("Table size update not at the start of the block")
                consumed = self._update_encoding_context(data_mem[current_index:])
                header = None
            else:
                header, consumed = self._decode_literal_no_index(data_mem[current_index:])
            if header:
                headers.append(header)
                inflated_size += table_entry_size(header[0], header[1])
                if inflated_size > self.max_header_list_size:
                    raise OversizedHeaderListError(
                        f"A header list larger than {self.max_header_list_size} has been received"
                    )
            current_index += consumed
        self._assert_valid_table_size()
        try:
            return [_unicode_if_needed(header, raw) for header in headers]
        except UnicodeDecodeError as error:
            raise HPACKDecodingError("Unable to decode headers as UTF-8") from error

    def _assert_valid_table_size(self):
        if self.header_table_size > self.max_allowed_table_size:
            raise InvalidTableSizeError("Encoder did not shrink table size to within the max")

    def _update_encoding_context(self, data):
        new_size, consumed = decode_integer(data, 5)
        if new_size > self.max_allowed_table_size:
            raise InvalidTableSizeError("Encoder exceeded max allowable table size")
        self.header_table_size = new_size
        return consumed

    def _decode_indexed(self, data):
        index, consumed = decode_integer(data, 7)
        return HeaderTuple(*self.header_table.get_by_index(index)), consumed

    def _decode_literal_no_index(self, data):
        return self._decode_literal(data, False)

    def _decode_literal_index(self, data):
        return self._decode_literal(data, True)

    def _decode_literal(self, data, should_index):
        if isinstance(data, memoryview):
            data = data.tobytes()
        try:
            if should_index:
                indexed_name = data[0] & 0x3F
                name_prefix = 6
                not_indexable = False
            else:
                indexed_name = data[0] & 0x0F
                name_prefix = 4
                not_indexable = bool(data[0] & 0x10)
        except IndexError as error:
            raise HPACKDecodingError("Truncated header block") from error

        if indexed_name:
            index, consumed = decode_integer(data, name_prefix)
            name = self.header_table.get_by_index(index)[0]
            total_consumed = consumed
            length = 0
        else:
            data = data[1:]
            length, consumed = decode_integer(data, 7)
            name = data[consumed : consumed + length]
            if len(name) != length:
                raise HPACKDecodingError("Truncated header block")
            if data[0] & 0x80:
                name = decode_huffman(name)
            total_consumed = consumed + length + 1

        data = data[consumed + length :]
        length, consumed = decode_integer(data, 7)
        value = data[consumed : consumed + length]
        if len(value) != length:
            raise HPACKDecodingError("Truncated header block")
        if data[0] & 0x80:
            value = decode_huffman(value)
        total_consumed += length + consumed

        cls = NeverIndexedHeaderTuple if not_indexable else HeaderTuple
        header = cls(name, value)
        if should_index:
            self.header_table.add(name, value)
        return header, total_consumed
