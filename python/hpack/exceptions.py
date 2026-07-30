"""Exceptions exposed by the upstream-compatible API."""


class HPACKError(Exception):
    pass


class HPACKDecodingError(HPACKError):
    pass


class InvalidTableIndexError(HPACKDecodingError):
    pass


class InvalidTableIndex(InvalidTableIndexError):
    pass


class OversizedHeaderListError(HPACKDecodingError):
    pass


class InvalidTableSizeError(HPACKDecodingError):
    pass
