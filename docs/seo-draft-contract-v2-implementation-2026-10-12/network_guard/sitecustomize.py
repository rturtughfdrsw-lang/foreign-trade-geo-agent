"""Test-process guard inherited by Python subprocesses; no external networking."""
import ipaddress
import os
import sys


def guard(event, args):
    if event not in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        return
    address = args[1] if event == 'socket.connect' else args[0]
    if event == 'socket.sendto':
        address = args[-1]
    host = address[0] if isinstance(address, tuple) else address
    if host in {'localhost', None}:
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    log = os.environ.get('DRAFT_V2_NETWORK_LOG')
    if log:
        with open(log, 'a', encoding='utf-8') as stream:
            stream.write(event + '\n')
    raise RuntimeError('OFFLINE_EXTERNAL_NETWORK_FORBIDDEN')


sys.addaudithook(guard)
