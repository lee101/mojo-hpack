"""Header tuple types carrying HPACK indexing metadata."""


class HeaderTuple(tuple):
    __slots__ = ()
    indexable = True

    def __new__(cls, *args):
        return tuple.__new__(cls, args)


class NeverIndexedHeaderTuple(HeaderTuple):
    __slots__ = ()
    indexable = False
