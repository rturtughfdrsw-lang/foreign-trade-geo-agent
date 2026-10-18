"""Fixed RSA-3072/SHA-256/PSS verification using Windows BCrypt.

Only public SPKI is accepted here. No private-key import, creation or discovery.
Signing belongs to the independently installed host, via its signer port.
"""
import ctypes
from dataclasses import dataclass
import hashlib
import struct
import sys


# DER rsaEncryption SPKI, fixed 3072-bit positive modulus, exponent 65537.
# This is format validation, not an implementation of RSA or PSS.
_SPKI_PREFIX = bytes.fromhex(
    "308201a2300d06092a864886f70d01010105000382018f003082018a0282018100")
_SPKI_SUFFIX = bytes.fromhex("0203010001")


class _PssInfo(ctypes.Structure):
    _fields_ = [("algorithm", ctypes.c_wchar_p), ("salt_length", ctypes.c_ulong)]


class _BCrypt:
    """Small native binding; no fallback algorithms or provider URLs."""
    def __init__(self):
        if sys.platform != "win32":
            raise ValueError("CNG_UNAVAILABLE")
        self.dll = ctypes.WinDLL("bcrypt.dll", winmode=0x00000800)
        ptr, uint = ctypes.c_void_p, ctypes.c_ulong
        signatures = {
            "BCryptOpenAlgorithmProvider": [ctypes.POINTER(ptr), ctypes.c_wchar_p, ctypes.c_wchar_p, uint],
            "BCryptCloseAlgorithmProvider": [ptr, uint],
            "BCryptImportKeyPair": [ptr, ptr, ctypes.c_wchar_p, ctypes.POINTER(ptr), ptr, uint, uint],
            "BCryptDestroyKey": [ptr],
            "BCryptVerifySignature": [ptr, ptr, ptr, uint, ptr, uint, uint],
            "BCryptGenerateKeyPair": [ptr, ctypes.POINTER(ptr), uint, uint],
            "BCryptFinalizeKeyPair": [ptr, uint],
            "BCryptExportKey": [ptr, ptr, ctypes.c_wchar_p, ptr, uint, ctypes.POINTER(uint), uint],
            "BCryptSignHash": [ptr, ptr, ptr, uint, ptr, uint, ctypes.POINTER(uint), uint],
        }
        for name, args in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = args, ctypes.c_long

    @staticmethod
    def check(status):
        if status != 0:
            raise ValueError("CNG_OPERATION_FAILED")

    def open(self):
        handle = ctypes.c_void_p()
        self.check(self.dll.BCryptOpenAlgorithmProvider(ctypes.byref(handle), "RSA", None, 0))
        return handle


@dataclass(frozen=True, slots=True)
class RsaPssPublicKey:
    spki: bytes

    def __post_init__(self):
        if (type(self.spki) is not bytes or len(self.spki) != 422
            or not self.spki.startswith(_SPKI_PREFIX) or not self.spki.endswith(_SPKI_SUFFIX)
            or not self.spki[len(_SPKI_PREFIX)] & 0x80
            or not self.spki[-len(_SPKI_SUFFIX)-1] & 1):
            raise ValueError("RSA_PUBLIC_ANCHOR_INVALID")

    @property
    def fingerprint(self):
        return hashlib.sha256(self.spki).hexdigest()

    def verify(self, message: bytes, signature: bytes) -> bool:
        if (type(message) is not bytes or not 0 < len(message) <= 160*1024
            or type(signature) is not bytes or len(signature) != 384):
            return False
        algorithm, key = None, ctypes.c_void_p()
        try:
            native = _BCrypt()
            algorithm = native.open()
            modulus = self.spki[len(_SPKI_PREFIX):-len(_SPKI_SUFFIX)]
            blob = struct.pack("<6I", 0x31415352, 3072, 3, 384, 0, 0) + b"\x01\x00\x01" + modulus
            buffer = ctypes.create_string_buffer(blob)
            native.check(native.dll.BCryptImportKeyPair(algorithm, None, "RSAPUBLICBLOB",
                ctypes.byref(key), buffer, len(blob), 0))
            digest = ctypes.create_string_buffer(hashlib.sha256(message).digest())
            proof = ctypes.create_string_buffer(signature)
            padding = _PssInfo("SHA256", 32)
            return native.dll.BCryptVerifySignature(key, ctypes.byref(padding), digest, 32,
                proof, 384, 8) == 0  # BCRYPT_PAD_PSS
        except Exception:
            return False
        finally:
            if key.value:
                native.dll.BCryptDestroyKey(key)
            if algorithm is not None:
                native.dll.BCryptCloseAlgorithmProvider(algorithm, 0)
