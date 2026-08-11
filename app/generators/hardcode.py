"""Camada Hardcode: ruído polimórfico inerte para builds genéricos Lua."""
from __future__ import annotations

import secrets


def inject_hardcode_noise(program, count=7):
    """Adiciona constantes e funções nunca chamadas, sem alterar o fluxo real."""
    program = {
        'constants': list(program.get('constants', [])),
        'instructions': [dict(item, args=list(item.get('args', []))) for item in program.get('instructions', [])],
        'functions': list(program.get('functions', [])),
        'blocks': list(program.get('blocks', [])),
    }
    for _ in range(max(1, count)):
        token = secrets.token_urlsafe(12)
        program['constants'].extend([
            f'HC_{token}',
            f'noise_{secrets.token_hex(8)}',
            secrets.token_hex(16),
        ])
        program['functions'].append({
            'params': [f'_h{secrets.token_hex(3)}'],
            'program': {
                'constants': [token, secrets.token_hex(8)],
                'instructions': [
                    {'op': 'CONST', 'args': [0], 'line': None},
                    {'op': 'POP', 'args': [], 'line': None},
                    {'op': 'HALT', 'args': [], 'line': None},
                ],
                'functions': [],
                'blocks': [],
            },
        })
    return program
