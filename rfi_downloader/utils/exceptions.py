from __future__ import annotations


class AlreadyRunning(Exception):
    pass


class AlreadyPaused(Exception):
    pass


class NotYetRunning(Exception):
    pass
