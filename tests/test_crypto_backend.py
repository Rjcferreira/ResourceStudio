import unittest

from app.generators.crypto_backend import (
    chacha20_block,
    chacha20_xor,
    constant_time_equal,
    open_payload,
    seal_payload,
    hkdf_sha256,
    hmac_sha256,
)


class CryptoBackendTests(unittest.TestCase):
    def test_chacha20_rfc8439_block(self):
        key = bytes.fromhex(
            '000102030405060708090a0b0c0d0e0f'
            '101112131415161718191a1b1c1d1e1f'
        )
        nonce = bytes.fromhex('000000090000004a00000000')
        expected = (
            '10f1e7e4d13b5915500fdd1fa32071c4'
            'c7d1f4c733c068030422aa9ac3d46c4e'
            'd2826446079faa0914c2d705d98b02a2'
            'b5129cd1de164eb9cbd083e8a2503c4e'
        )
        self.assertEqual(chacha20_block(key, 1, nonce).hex(), expected)

    def test_chacha20_round_trip(self):
        key = bytes(range(32))
        nonce = bytes.fromhex('000000000000000000000001')
        payload = b'ResourceStudio Hardcode test payload'
        encrypted = chacha20_xor(key, nonce, payload)
        self.assertNotEqual(encrypted, payload)
        self.assertEqual(chacha20_xor(key, nonce, encrypted), payload)

    def test_hkdf_rfc5869_sha256(self):
        ikm = bytes.fromhex('0b' * 22)
        salt = bytes.fromhex('000102030405060708090a0b0c')
        info = bytes.fromhex('f0f1f2f3f4f5f6f7f8f9')
        expected = (
            '3cb25f25faacd57a90434f64d0362f2a'
            '2d2d0a90cf1a5a4c5db02d56ecc4c5bf'
            '34007208d5b887185865'
        )
        self.assertEqual(hkdf_sha256(ikm, salt, info, 42).hex(), expected)

    def test_hmac_and_constant_time_compare(self):
        tag = hmac_sha256(b'key', b'The quick brown fox jumps over the lazy dog')
        self.assertEqual(
            tag.hex(),
            'f7bc83f430538424b13298e6aa6fb143'
            'ef4d59a14946175997479dbc2d1a3cd8',
        )
        self.assertTrue(constant_time_equal(tag, tag[:]))
        self.assertFalse(constant_time_equal(tag, tag[:-1] + b'0'))

    def test_seal_open_and_tamper_rejection(self):
        secret = b'local-only-server-secret'
        envelope = seal_payload(
            secret,
            b'bytecode-payload',
            salt=bytes.fromhex('00112233445566778899aabbccddeeff'),
            nonce=bytes.fromhex('000102030405060708090a0b'),
        )
        self.assertEqual(open_payload(secret, envelope), b'bytecode-payload')
        tampered = dict(envelope)
        tampered['ciphertext'] = bytes([tampered['ciphertext'][0] ^ 1]) + tampered['ciphertext'][1:]
        with self.assertRaises(ValueError):
            open_payload(secret, tampered)


if __name__ == '__main__':
    unittest.main()
