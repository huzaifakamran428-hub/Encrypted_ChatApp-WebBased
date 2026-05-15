"""
encryption.py — AES-256 CBC Encryption/Decryption
===================================================
Implements the encryption model from the Information Security Project Proposal:

    C = E_k(M)

Where:
  M = Original plaintext message
  C = Encrypted ciphertext
  k = Secret 256-bit AES key (stored in settings.ENCRYPTION_KEY)

Each message gets a unique 16-byte IV (Initialization Vector) so that
identical messages produce different ciphertexts. The IV is stored
alongside the ciphertext in the database (it is not secret).

Algorithm  : AES-256-CBC
Key size   : 256 bits (32 bytes)
Block size : 128 bits (16 bytes)
IV size    : 128 bits (16 bytes) — unique per message
Padding    : PKCS7
"""

import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from django.conf import settings


def _get_key() -> bytes:
    """Return the 32-byte AES key from settings."""
    key_hex = getattr(settings, 'ENCRYPTION_KEY', '')
    if not key_hex:
        raise ValueError("ENCRYPTION_KEY is not set in settings.py")
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise ValueError("ENCRYPTION_KEY must be exactly 32 bytes (64 hex chars) for AES-256")
    return key


def encrypt_message(plaintext: str) -> tuple[str, str]:
    """
    Encrypt a plaintext string using AES-256-CBC.

    Returns:
        (ciphertext_b64, iv_b64) — both base64-encoded strings safe for DB storage
    """
    if not plaintext:
        return ('', '')

    key = _get_key()
    iv  = os.urandom(16)                         # unique IV per message

    padder    = padding.PKCS7(128).padder()
    padded    = padder.update(plaintext.encode('utf-8')) + padder.finalize()

    cipher    = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ct_bytes  = encryptor.update(padded) + encryptor.finalize()

    return (
        base64.b64encode(ct_bytes).decode('utf-8'),
        base64.b64encode(iv).decode('utf-8'),
    )


def decrypt_message(ciphertext_b64: str, iv_b64: str) -> str:
    """
    Decrypt a base64-encoded AES-256-CBC ciphertext.

    Returns the original plaintext string, or '[Encrypted]' if decryption fails.
    """
    if not ciphertext_b64 or not iv_b64:
        return ''

    try:
        key      = _get_key()
        ct_bytes = base64.b64decode(ciphertext_b64)
        iv       = base64.b64decode(iv_b64)

        cipher    = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded    = decryptor.update(ct_bytes) + decryptor.finalize()

        unpadder  = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()

        return plaintext.decode('utf-8')
    except Exception:
        return '[Encrypted message — decryption failed]'


def encrypt_file_path(file_path: str) -> tuple[str, str]:
    """Encrypt a file path string (for encrypted_file_path field)."""
    return encrypt_message(file_path)


def decrypt_file_path(encrypted_path: str, iv: str) -> str:
    """Decrypt a file path string."""
    return decrypt_message(encrypted_path, iv)
