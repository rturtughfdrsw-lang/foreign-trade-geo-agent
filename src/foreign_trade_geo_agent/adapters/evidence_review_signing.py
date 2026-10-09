"""Host-only RSA-PSS signing adapter for an already-owned BCrypt key capability.

Does not create/open/import/export private keys or discover keys by name. The
independent host key provider owns handle lifetime and custody. Production named
NCrypt key opening/custody remains a deployment adapter gap, never auto-bootstrap.
"""
import ctypes
import hashlib

from .evidence_review_cng import _BCrypt, _PssInfo, RsaPssPublicKey


class BCryptRsaPssSigner:
    def __init__(self, *, key_handle: ctypes.c_void_p, public_key: RsaPssPublicKey):
        if type(key_handle) is not ctypes.c_void_p or not key_handle.value or type(public_key) is not RsaPssPublicKey:
            raise ValueError("HOST_SIGNING_CAPABILITY_REQUIRED")
        self._key, self.public_key, self._native = key_handle, public_key, _BCrypt()

    def sign(self, message: bytes) -> bytes:
        try:
            if type(message) is not bytes or not 0 < len(message) <= 160*1024:
                raise ValueError()
            digest = ctypes.create_string_buffer(hashlib.sha256(message).digest())
            padding, size = _PssInfo("SHA256", 32), ctypes.c_ulong()
            output = ctypes.create_string_buffer(384)
            self._native.check(self._native.dll.BCryptSignHash(self._key, ctypes.byref(padding), digest, 32,
                output, 384, ctypes.byref(size), 8))
            proof = output.raw
            if size.value != 384 or not self.public_key.verify(message, proof):
                raise ValueError()
            return proof
        except Exception:
            raise ValueError("HOST_SIGNATURE_FAILED") from None
