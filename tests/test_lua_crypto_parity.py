import hashlib
import unittest

try:
    from lupa import LuaRuntime
except ImportError:  # Dependência opcional, usada apenas para validação local.
    LuaRuntime = None

from app.generators.crypto_backend import (
    chacha20_block,
    hmac_sha256,
    hkdf_sha256,
    seal_payload,
)
from app.generators.lua_crypto_runtime import LUA_CRYPTO_RUNTIME


@unittest.skipUnless(LuaRuntime, 'lupa não instalado; paridade Lua opcional')
class LuaCryptoParityTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.crypto = self.lua.execute(LUA_CRYPTO_RUNTIME)

    def test_hash_kdf_and_chacha_match_python(self):
        key = bytes.fromhex(
            '000102030405060708090a0b0c0d0e0f'
            '101112131415161718191a1b1c1d1e1f'
        )
        nonce = bytes.fromhex('000000090000004a00000000')
        self.assertEqual(self.crypto.sha256(b'ResourceStudio'), hashlib.sha256(b'ResourceStudio').digest())
        self.assertEqual(self.crypto.hmac(b'key', b'payload'), hmac_sha256(b'key', b'payload'))
        ikm = bytes.fromhex('0b' * 22)
        salt = bytes.fromhex('000102030405060708090a0b0c')
        info = bytes.fromhex('f0f1f2f3f4f5f6f7f8f9')
        self.assertEqual(self.crypto.hkdf(ikm, salt, info, 42), hkdf_sha256(ikm, salt, info, 42))
        self.assertEqual(self.crypto.chacha_block(key, 1, nonce), chacha20_block(key, 1, nonce))

    def test_envelope_opens_in_lua(self):
        secret = b'local-only-server-secret'
        payload = b'bytecode-payload'
        envelope = seal_payload(
            secret,
            payload,
            salt=bytes.fromhex('00112233445566778899aabbccddeeff'),
            nonce=bytes.fromhex('000102030405060708090a0b'),
        )
        opened, error = self.crypto.open(
            secret,
            envelope['salt'],
            envelope['nonce'],
            envelope['ciphertext'],
            envelope['tag'],
        )
        self.assertIsNone(error)
        self.assertEqual(opened, payload)


if __name__ == '__main__':
    unittest.main()
