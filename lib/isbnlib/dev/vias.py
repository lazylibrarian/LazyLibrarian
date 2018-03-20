# -*- coding: utf-8 -*-
"""Process tasks in several modes."""

import logging

from .. import config

LOGGER = logging.getLogger(__name__)


def serial(named_tasks, arg):
    """Serial calls."""
    results = {}
    for name, task in named_tasks:
        try:
            results[name] = task(arg)
        except:  # pragma: no cover
            LOGGER.debug("No result in 'serial' for %s[%s](%s)", task, name,
                         arg)
            results[name] = None
    return results


def parallel(named_tasks, arg):
    """Threaded calls."""
    from threading import Thread
    results = {}

    def _worker(name, task, arg):
        try:
            results[name] = task(arg)
        except:  # pragma: no cover
            LOGGER.debug("No result in 'parallel' for %s[%s](%s)", task, name,
                         arg)
            results[name] = None

    for name, task in named_tasks:
        t = Thread(target=_worker, args=(name, task, arg))
        t.start()
        t.join(config.THREADS_TIMEOUT)
    return results


def multi(named_tasks, arg):
    """Multiprocessing: using several cores (if available)."""
    from multiprocessing import Process, Queue
    results = {}
    q = Queue()

    def _worker(name, task, arg, q):
        try:  # pragma: no cover
            q.put((name, task(arg)))
        except:  # pragma: no cover
            LOGGER.debug("No result in 'multi' for %s[%s](%s)", task, name,
                         arg)
            q.put((name, None))

    for name, task in named_tasks:
        p = Process(target=_worker, args=(name, task, arg, q))
        p.start()
        p.join(config.THREADS_TIMEOUT)
    q.put('STOP')

    while True:
        el = q.get()
        if el == 'STOP':
            break
        results[el[0]] = el[1]
    return results
