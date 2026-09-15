"""Offline test process guard; inherited by Python subprocesses via PYTHONPATH."""
import socket

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_sendto = socket.socket.sendto


def _connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError("OFFLINE_GUARD: network connections disabled")
    return _original_connect(self, address)


def _connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError("OFFLINE_GUARD: network connections disabled")
    return _original_connect_ex(self, address)


def _sendto(self, *args):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError("OFFLINE_GUARD: datagrams disabled")
    return _original_sendto(self, *args)


socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.socket.sendto = _sendto
