"""RFC 7541 static and dynamic header tables."""

from collections import deque

from .exceptions import InvalidTableIndex


def table_entry_size(name: bytes, value: bytes) -> int:
    return 32 + len(name) + len(value)


class HeaderTable:
    DEFAULT_SIZE = 4096
    STATIC_TABLE = (
        (b":authority", b""), (b":method", b"GET"), (b":method", b"POST"),
        (b":path", b"/"), (b":path", b"/index.html"), (b":scheme", b"http"),
        (b":scheme", b"https"), (b":status", b"200"), (b":status", b"204"),
        (b":status", b"206"), (b":status", b"304"), (b":status", b"400"),
        (b":status", b"404"), (b":status", b"500"), (b"accept-charset", b""),
        (b"accept-encoding", b"gzip, deflate"), (b"accept-language", b""),
        (b"accept-ranges", b""), (b"accept", b""),
        (b"access-control-allow-origin", b""), (b"age", b""), (b"allow", b""),
        (b"authorization", b""), (b"cache-control", b""),
        (b"content-disposition", b""), (b"content-encoding", b""),
        (b"content-language", b""), (b"content-length", b""),
        (b"content-location", b""), (b"content-range", b""),
        (b"content-type", b""), (b"cookie", b""), (b"date", b""),
        (b"etag", b""), (b"expect", b""), (b"expires", b""), (b"from", b""),
        (b"host", b""), (b"if-match", b""), (b"if-modified-since", b""),
        (b"if-none-match", b""), (b"if-range", b""),
        (b"if-unmodified-since", b""), (b"last-modified", b""), (b"link", b""),
        (b"location", b""), (b"max-forwards", b""),
        (b"proxy-authenticate", b""), (b"proxy-authorization", b""),
        (b"range", b""), (b"referer", b""), (b"refresh", b""),
        (b"retry-after", b""), (b"server", b""), (b"set-cookie", b""),
        (b"strict-transport-security", b""), (b"transfer-encoding", b""),
        (b"user-agent", b""), (b"vary", b""), (b"via", b""),
        (b"www-authenticate", b""),
    )
    STATIC_TABLE_LENGTH = len(STATIC_TABLE)

    def __init__(self):
        self._maxsize = self.DEFAULT_SIZE
        self._current_size = 0
        self.resized = False
        self.dynamic_entries = deque()

    def get_by_index(self, index):
        original = index
        index -= 1
        if 0 <= index < self.STATIC_TABLE_LENGTH:
            return self.STATIC_TABLE[index]
        index -= self.STATIC_TABLE_LENGTH
        if 0 <= index < len(self.dynamic_entries):
            return self.dynamic_entries[index]
        raise InvalidTableIndex(f"Invalid table index {original}")

    def __repr__(self):
        return f"HeaderTable({self._maxsize}, {self.resized}, {self.dynamic_entries!r})"

    def add(self, name, value):
        size = table_entry_size(name, value)
        if size > self._maxsize:
            self.dynamic_entries.clear()
            self._current_size = 0
            return
        self.dynamic_entries.appendleft((name, value))
        self._current_size += size
        self._shrink()

    def search(self, name, value):
        partial = None
        static = self.STATIC_TABLE_MAPPING.get(name)
        if static:
            index = static[1].get(value)
            if index is not None:
                return index, name, value
            partial = (static[0], name, None)
        offset = self.STATIC_TABLE_LENGTH + 1
        for index, (entry_name, entry_value) in enumerate(self.dynamic_entries):
            if entry_name == name:
                if entry_value == value:
                    return index + offset, entry_name, entry_value
                if partial is None:
                    partial = (index + offset, entry_name, None)
        return partial

    @property
    def maxsize(self):
        return self._maxsize

    @maxsize.setter
    def maxsize(self, value):
        value = int(value)
        old = self._maxsize
        self._maxsize = value
        self.resized = value != old
        if value <= 0:
            self.dynamic_entries.clear()
            self._current_size = 0
        elif old > value:
            self._shrink()

    def _shrink(self):
        while self._current_size > self._maxsize:
            name, value = self.dynamic_entries.pop()
            self._current_size -= table_entry_size(name, value)


def _static_mapping():
    result = {}
    for index, (name, value) in enumerate(HeaderTable.STATIC_TABLE, 1):
        entry = result.setdefault(name, (index, {}))
        entry[1][value] = index
    return result


HeaderTable.STATIC_TABLE_MAPPING = _static_mapping()
