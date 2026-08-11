import unittest
import re

try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime = None

from luaparser import ast

from app.generators.lua_bytecode import Compiler, render_vm


@unittest.skipUnless(LuaRuntime, 'lupa não instalado; smoke test opcional')
class VmRuntimeTests(unittest.TestCase):
    def test_generated_vm_runs_without_load(self):
        program = Compiler().compile(ast.parse('local value = 1 + 2'))
        secret = 'smoke-test-secret'
        code = render_vm(program, 'rs_secret_smoke', secret).encode()
        self.assertNotIn(b'load(', code)

        lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        prelude = b"GetConvar=function(a,b)return '" + secret.encode() + b"' end;"
        self.assertIsNone(lua.execute(prelude + code))

    def test_generated_vm_rejects_tampered_bytecode(self):
        program = Compiler().compile(ast.parse('local value = 1 + 2'))
        secret = 'smoke-test-secret'
        code = render_vm(program, 'rs_secret_smoke', secret)
        match = re.search(r'(\["h[a-f0-9]{6}"\]=")([A-Za-z0-9+/=]{50,})(")', code)
        self.assertIsNotNone(match)
        original = match.group(2)
        changed = ('A' if original[0] != 'A' else 'B') + original[1:]
        tampered = code[:match.start(2)] + changed + code[match.end(2):]

        lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        prelude = b"GetConvar=function(a,b)return '" + secret.encode() + b"' end;"
        with self.assertRaises(Exception):
            lua.execute(prelude + tampered.encode())


if __name__ == '__main__':
    unittest.main()
