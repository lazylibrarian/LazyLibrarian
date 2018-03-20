# -*- coding: utf-8 -*-
"""DEPRECATED Read and write shelve cache.

NOTES
1. shelve has different incompatible formats in py2 and py3.
2. If some methods detect that the cache is not consistent
   they delete the cache and create a new one.
3. After purge, the cache keeps the records with more hits
   and the newests.
4. By opening and closing in each operation, the cache performs badly
   for many records (because it doesn't use the 'in memory' part of cache).
   So don't increase MAXLEN too much.
5. The cache is optimized for low hit frequency (using a simple dict lookup
   not a Bloom filter!).

"""

# DEPRECATED (delete on 3.9.0)

import datetime
import shelve
from time import time as timestamp


class ShelveCache(object):
    """Read and write shelve cache."""

    MAXLEN = 2000
    CUTOFF = 0.5

    def __init__(self, filepath):
        """Initialize attributes."""
        self._sh = shelve
        self.filepath = filepath
        try:
            s = self._sh.open(self.filepath)
            try:
                self._keys = list(s.keys())
                if len(self._keys) > self.MAXLEN:
                    self.purge()
            except:
                pass
        except:
            s = self._sh.open(self.filepath, 'n')
            self._keys = []
        finally:
            s.close()

    def __getitem__(self, key):
        """Read cache."""
        if key not in self._keys:
            return None
        try:
            s = self._sh.open(self.filepath, writeback=True)
            if s[key]:
                s[key]['hits'] += 1
                return s[key]['value']
            else:
                return None
        except ValueError:
            s = self._sh.open(self.filepath, 'n')
            self._keys = []
            return None
        finally:
            s.close()

    def __setitem__(self, key, value):
        """Write to cache."""
        try:
            s = self._sh.open(self.filepath)
            s[key] = {'value': value, 'hits': 0, 'timestamp': timestamp()}
            self._keys.append(key)
            status = True
        except:
            status = False
        finally:
            s.close()
        return status

    def __delitem__(self, key):
        """Delete record with key."""
        if key not in self._keys:
            return
        try:
            s = self._sh.open(self.filepath)
            del s[key]
            self._keys.remove(key)
        except ValueError:
            s = self._sh.open(self.filepath, 'n')
            self._keys = []
            return
        finally:
            s.close()

    def __len__(self):
        """Return the number of keys in cache."""
        return len(self.keys()) if self.keys() else 0

    def __call__(self, key):
        """Allow an alternative way to access items."""
        return self.__getitem__(key)

    def keys(self):
        """Return list of keys in Cache."""
        if self._keys:
            return self._keys
        try:
            s = self._sh.open(self.filepath)
            self._keys = list(s.keys())
            return self._keys
        finally:
            s.close()

    def ts(self, key):
        """Return the timestamp of the record with key."""
        if key not in self._keys:
            return None
        try:
            s = self._sh.open(self.filepath)
            ts = s[key]['timestamp'] if s[key] else None
            if not ts:
                return
            fmt = '%Y-%m-%d %H:%M:%S'
            return datetime.datetime.fromtimestamp(ts).strftime(fmt)
        except ValueError:
            s = self._sh.open(self.filepath, 'n')
            self._keys = []
            return
        finally:
            s.close()

    def hits(self, key):
        """Return the number of hits for the record with key."""
        if key not in self._keys:
            return None
        try:
            s = self._sh.open(self.filepath)
            hts = s[key]['hits'] if s[key] else None
            return hts
        except ValueError:
            s = self._sh.open(self.filepath, 'n')
            self._keys = []
            return
        finally:
            s.close()

    def new(self):
        """Make new cache."""
        s = self._sh.open(self.filepath, 'n')
        self._keys = []
        s.close()

    def purge(self):
        """Purge the cache."""
        if len(self.keys()) < self.MAXLEN:
            return
        try:
            s = self._sh.open(self.filepath)
            data = [(k, s[k]['timestamp'], s[k]['hits']) for k in s.keys()]
            data.sort(key=lambda tup: (-tup[2], -tup[1]))
            keep = int(self.CUTOFF * self.MAXLEN)
            garbk = [k[0] for k in data[keep:]]
            for k in garbk:
                del s[k]
            self._keys = s.keys()
        finally:
            s.close()
