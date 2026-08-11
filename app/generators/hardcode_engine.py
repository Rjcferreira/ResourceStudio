"""Entrada independente do módulo Hardcode avançado.

O motor é mantido atrás desta fronteira para que a evolução da VM não altere
os três modelos FiveM existentes nem as suas rotas do painel.
"""
from app.generators.lua_bytecode import compile_lua_bytecode


def compile_hardcode(root_value, source_file, preview=False):
    result = compile_lua_bytecode(
        root_value,
        source_file,
        preview,
        output_suffix='_hardcode',
        secret_prefix='rs_hardcode_secret',
        server_only=False,
        hardcore=True,
    )
    result['format'] = 'resource-studio-hardcode'
    result['module'] = 'hardcode-advanced'
    result['level'] = 'hardcode'
    return result
