"""Block external sockets/DNS in this test process and Python children."""
import ipaddress
import os
import sys


def guard(event, args):
    if event not in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        return
    address = args[1] if event == 'socket.connect' else args[-1] if event == 'socket.sendto' else args[0]
    host = address[0] if isinstance(address, tuple) else address
    if host in {'localhost', None}:
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    log = os.environ.get('DRAFT_V3_NETWORK_LOG')
    if log:
        with open(log, 'a', encoding='utf-8') as stream:
            stream.write(event + '\n')
    raise RuntimeError('V3_OFFLINE_EXTERNAL_NETWORK_FORBIDDEN')


sys.addaudithook(guard)
