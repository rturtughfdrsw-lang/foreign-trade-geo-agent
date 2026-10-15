"""Block external Python sockets/DNS, inherited by Python test subprocesses.

Only loopback is allowed for existing HTTP server unit tests. PREFLIGHT_STRICT=1
also blocks loopback; used for preflight-specific and contract-specific tests.
"""
import ipaddress
import os
import sys


def guard(event, args):
    if event not in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        return
    address = args[1] if event == 'socket.connect' else args[-1] if event == 'socket.sendto' else args[0]
    host = address[0] if isinstance(address, tuple) else address
    loopback = host == 'localhost'
    try:
        loopback = loopback or ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        pass
    allowed = loopback and os.environ.get('PREFLIGHT_STRICT') != '1'
    log = os.environ.get('FLASH_PREFLIGHT_NETWORK_LOG')
    if log:
        with open(log, 'a', encoding='utf-8') as stream:
            stream.write(('loopback_allowed:' if allowed else 'blocked:') + event + '\n')
    if not allowed:
        raise RuntimeError('PREFLIGHT_NETWORK_FORBIDDEN')


sys.addaudithook(guard)
