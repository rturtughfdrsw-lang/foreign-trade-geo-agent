import asyncio
from collections.abc import Iterable
from pathlib import Path
import socket
import ssl
import threading
import unittest
from unittest.mock import patch

import httpcore
import httpx

from foreign_trade_geo_agent.adapters.safe_http import _PinnedAsyncHTTPTransport


FIXTURES = Path(__file__).parent / "fixtures" / "safe_http"


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self._delegate = httpcore.AnyIOBackend()
        self.tcp_targets: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.tcp_targets.append((host, port))
        return await self._delegate.connect_tcp(
            host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("Unix sockets are not allowed by the safe HTTP transport.")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class _LocalServer:
    def __init__(self, *, tls: bool = False) -> None:
        self._tls = tls
        self.server: asyncio.Server | None = None
        self.host_headers: list[str] = []
        self.sni_names: list[str | None] = []

    async def __aenter__(self) -> "_LocalServer":
        context = None
        if self._tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(
                FIXTURES / "safe-test-cert.pem",
                FIXTURES / "safe-test-key.pem",
            )
            context.set_servername_callback(
                lambda _socket, name, _context: self.sni_names.append(name)
            )
        self.server = await asyncio.start_server(
            self._handle,
            "127.0.0.1",
            0,
            ssl=context,
        )
        return self

    async def __aexit__(self, *_args: object) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.sockets[0].getsockname()[1])

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            header_block = await reader.readuntil(b"\r\n\r\n")
            for line in header_block.decode("ascii").split("\r\n"):
                if line.casefold().startswith("host:"):
                    self.host_headers.append(line.split(":", 1)[1].strip())
            body = b"<html><body>local proof</body></html>"
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


class _HangingTLSServer:
    def __init__(self) -> None:
        self.connected = threading.Event()
        self.eof_received = threading.Event()
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen()
        self._listener.settimeout(0.05)
        self._connection: socket.socket | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    async def __aenter__(self) -> "_HangingTLSServer":
        self._thread.start()
        return self

    async def __aexit__(self, *_args: object) -> None:
        self._stop.set()
        self._listener.close()
        if self._connection is not None:
            self._connection.close()
        await asyncio.to_thread(self._thread.join, 0.5)

    @property
    def port(self) -> int:
        return int(self._listener.getsockname()[1])

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    connection, _address = self._listener.accept()
                    break
                except TimeoutError:
                    continue
                except OSError:
                    return
            else:
                return
            self._connection = connection
            connection.settimeout(0.05)
            self.connected.set()
            while not self._stop.is_set():
                try:
                    data = connection.recv(64 * 1024)
                except TimeoutError:
                    continue
                except OSError:
                    return
                if not data:
                    self.eof_received.set()
                    return
        finally:
            if self._connection is not None:
                self._connection.close()


class PinnedHTTPTransportIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_transport_rejects_unaudited_dependency_versions(self) -> None:
        with patch(
            "foreign_trade_geo_agent.adapters.safe_http.httpx.__version__",
            "0.29.0",
        ):
            with self.assertRaisesRegex(RuntimeError, "audited HTTPX/httpcore"):
                _PinnedAsyncHTTPTransport(
                    logical_host="safe.test",
                    logical_port=443,
                    validated_ip="127.0.0.1",
                )

    async def test_http_connects_to_pinned_ip_while_preserving_logical_url_and_host(self) -> None:
        async with _LocalServer() as server:
            server_port = server.port
            backend = _RecordingBackend()
            transport = _PinnedAsyncHTTPTransport(
                logical_host="safe.test",
                logical_port=server_port,
                validated_ip="127.0.0.1",
                network_backend=backend,
            )
            original_getaddrinfo = socket.getaddrinfo

            def guarded_getaddrinfo(host: object, *args: object, **kwargs: object):
                if host == "safe.test":
                    raise AssertionError("The connection stage re-resolved the logical host.")
                return original_getaddrinfo(host, *args, **kwargs)

            with patch("socket.getaddrinfo", side_effect=guarded_getaddrinfo):
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    response = await client.get(f"http://safe.test:{server_port}/proof")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.url.host, "safe.test")
        self.assertEqual(backend.tcp_targets, [("127.0.0.1", server_port)])
        self.assertEqual(server.host_headers, [f"safe.test:{server_port}"])

    async def test_https_connects_to_pinned_ip_with_original_host_sni_and_certificate_name(self) -> None:
        async with _LocalServer(tls=True) as server:
            server_port = server.port
            backend = _RecordingBackend()
            client_context = ssl.create_default_context(
                cafile=str(FIXTURES / "safe-test-cert.pem")
            )
            transport = _PinnedAsyncHTTPTransport(
                logical_host="safe.test",
                logical_port=server_port,
                validated_ip="127.0.0.1",
                ssl_context=client_context,
                network_backend=backend,
            )
            async with httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = await client.get(f"https://safe.test:{server_port}/proof")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.url.host, "safe.test")
        self.assertEqual(backend.tcp_targets, [("127.0.0.1", server_port)])
        self.assertEqual(server.host_headers, [f"safe.test:{server_port}"])
        self.assertEqual(server.sni_names, ["safe.test"])

    async def test_https_rejects_certificate_for_a_different_logical_host(self) -> None:
        async with _LocalServer(tls=True) as server:
            client_context = ssl.create_default_context(
                cafile=str(FIXTURES / "safe-test-cert.pem")
            )
            transport = _PinnedAsyncHTTPTransport(
                logical_host="wrong.test",
                logical_port=server.port,
                validated_ip="127.0.0.1",
                ssl_context=client_context,
            )
            async with httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                with self.assertRaises(httpx.ConnectError):
                    await client.get(f"https://wrong.test:{server.port}/proof")

        self.assertEqual(server.sni_names, ["wrong.test"])

    def test_transport_rejects_an_insecure_ssl_context(self) -> None:
        insecure_context = ssl.create_default_context()
        insecure_context.check_hostname = False
        insecure_context.verify_mode = ssl.CERT_NONE

        with self.assertRaisesRegex(ValueError, "certificate verification"):
            _PinnedAsyncHTTPTransport(
                logical_host="safe.test",
                logical_port=443,
                validated_ip="127.0.0.1",
                ssl_context=insecure_context,
            )

    async def test_outer_tls_handshake_timeout_closes_the_connected_tcp_stream(self) -> None:
        async with _HangingTLSServer() as server:
            transport = _PinnedAsyncHTTPTransport(
                logical_host="safe.test",
                logical_port=server.port,
                validated_ip="127.0.0.1",
            )
            client = httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                timeout=5.0,
            )
            try:
                with self.assertRaises(TimeoutError):
                    async with asyncio.timeout(0.05):
                        await client.get(f"https://safe.test:{server.port}/")
                connected = await asyncio.to_thread(server.connected.wait, 0.2)
                self.assertTrue(connected)
                closed = await asyncio.to_thread(server.eof_received.wait, 0.2)
            finally:
                try:
                    async with asyncio.timeout(0.2):
                        await client.aclose()
                except TimeoutError:
                    pass

        self.assertTrue(closed, "TLS cancellation leaked the connected TCP stream.")


if __name__ == "__main__":
    unittest.main()
