# -*- coding: utf-8 -*-
"""Read and write to a dict-like cache."""

from collections import MutableMapping


class IMCache(MutableMapping):
    """Read and write to a dict-like cache."""

    MAXLEN = 1000

    def __init__(self, maxlen=MAXLEN, *a, **k):
        self.filepath = 'IN MEMORY'
        self.maxlen = maxlen
        self.d = dict(*a, **k)
        while len(self) > maxlen:  # pragma: no cache
            self.popitem()

    def __iter__(self):
        return iter(self.d)

    def __len__(self):
        return len(self.d)

    def __getitem__(self, k):
        return self.d[k]

    def __setitem__(self, k, v):
        if k not in self and len(self) == self.maxlen:
            self.popitem()
        self.d[k] = v

    def __delitem__(self, k):
        del self.d[k]

    def __bool__(self):
        return len(self) != 0

    # For PY2 compatibility
    __nonzero__ = __bool__

    def __call__(self, k):
        try:
            return self.__getitem__(k)
        except KeyError:
            return None
