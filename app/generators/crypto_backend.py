"""Primitivas standard para o backend do Hardcode.

O módulo não altera ainda o formato VM; serve como núcleo testável para a
integração ChaCha20/HKDF/HMAC, evitando uma implementação ad-hoc no gerador.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets


def hkdf_sha256(secret: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    prk = hmac.new(salt or (b'\0' * 32), secret, hashlib.sha256).digest()
    output, previous = bytearray(), b''
    counter = 1
    while len(output) < length:
        previous = hmac.new(prk, previous + info + bytes([counter]), hashlib.sha256).digest()
        output.extend(previous)
        counter += 1
    return bytes(output[:length])


def hmac_sha256(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def constant_time_equal(left: bytes, right: bytes) -> bool:
    """Compara tags sem revelar o ponto da primeira diferença."""
    return hmac.compare_digest(left, right)


def derive_keys(secret: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """Deriva chaves independentes para cifra e autenticação."""
    material = hkdf_sha256(secret, salt, b'ResourceStudio Hardcode v1', 64)
    return material[:32], material[32:]


def seal_payload(secret: bytes, payload: bytes, salt: bytes | None = None,
                 nonce: bytes | None = None) -> dict[str, bytes]:
    """Cifra e autentica um payload com Encrypt-then-MAC.

    O salt e o nonce são públicos e devem ser guardados junto do payload.
    A chave continua exclusivamente no segredo externo do servidor.
    """
    salt = salt or secrets.token_bytes(16)
    nonce = nonce or secrets.token_bytes(12)
    if len(salt) != 16 or len(nonce) != 12:
        raise ValueError('salt deve ter 16 bytes e nonce 12 bytes')
    encryption_key, mac_key = derive_keys(secret, salt)
    ciphertext = chacha20_xor(encryption_key, nonce, payload)
    authenticated = b'RS-HC1' + salt + nonce + ciphertext
    return {'salt': salt, 'nonce': nonce, 'ciphertext': ciphertext,
            'tag': hmac_sha256(mac_key, authenticated)}


def open_payload(secret: bytes, envelope: dict[str, bytes]) -> bytes:
    """Valida primeiro a tag e só depois revela o payload."""
    salt, nonce = envelope['salt'], envelope['nonce']
    ciphertext, tag = envelope['ciphertext'], envelope['tag']
    encryption_key, mac_key = derive_keys(secret, salt)
    authenticated = b'RS-HC1' + salt + nonce + ciphertext
    expected = hmac_sha256(mac_key, authenticated)
    if not constant_time_equal(expected, tag):
        raise ValueError('tag de integridade inválida')
    return chacha20_xor(encryption_key, nonce, ciphertext)


def chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError('ChaCha20 requer chave de 32 bytes e nonce de 12 bytes')
    words = lambda data: list(int.from_bytes(data[i:i + 4], 'little') for i in range(0, len(data), 4))
    state = [0x61707865, 0x3320646e, 0x79622d32, 0x6b206574, *words(key), counter & 0xffffffff, *words(nonce)]
    original = state[:]
    mask = 0xffffffff

    def rotl(value, amount):
        return ((value << amount) | (value >> (32 - amount))) & mask

    def quarter(a, b, c, d):
        state[a] = (state[a] + state[b]) & mask; state[d] = rotl(state[d] ^ state[a], 16)
        state[c] = (state[c] + state[d]) & mask; state[b] = rotl(state[b] ^ state[c], 12)
        state[a] = (state[a] + state[b]) & mask; state[d] = rotl(state[d] ^ state[a], 8)
        state[c] = (state[c] + state[d]) & mask; state[b] = rotl(state[b] ^ state[c], 7)

    for _ in range(10):
        quarter(0, 4, 8, 12); quarter(1, 5, 9, 13); quarter(2, 6, 10, 14); quarter(3, 7, 11, 15)
        quarter(0, 5, 10, 15); quarter(1, 6, 11, 12); quarter(2, 7, 8, 13); quarter(3, 4, 9, 14)
    return b''.join(((state[i] + original[i]) & mask).to_bytes(4, 'little') for i in range(16))


def chacha20_xor(key: bytes, nonce: bytes, payload: bytes, counter: int = 1) -> bytes:
    result = bytearray()
    for offset in range(0, len(payload), 64):
        stream = chacha20_block(key, counter + offset // 64, nonce)
        result.extend(a ^ b for a, b in zip(payload[offset:offset + 64], stream))
    return bytes(result)
