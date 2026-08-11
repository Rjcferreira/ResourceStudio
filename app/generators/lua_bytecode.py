"""Primeira camada do compilador de bytecode ResourceStudio.

Este módulo ainda não executa Lua nem substitui o Lua Protector. Produz um
formato intermédio próprio para a futura VM e recusa construções que ainda não
estão implementadas, evitando gerar recursos aparentemente protegidos mas
incompatíveis.
"""
from __future__ import annotations

import json
import base64
import hashlib
import re
import secrets
import sys
from pathlib import Path

# O compilador carrega as suas dependências a partir da própria pasta do
# ResourceStudio, permitindo mover o projeto para outro computador.
_LOCAL_DEPS = Path(__file__).resolve().parents[2] / 'local_deps'
if str(_LOCAL_DEPS) not in sys.path:
    sys.path.insert(0, str(_LOCAL_DEPS))

from luaparser import ast
from luaparser.astnodes import (
    Assign,
    BinaryOp,
    Break,
    Call,
    Field,
    FalseExpr,
    Forin,
    Fornum,
    Function,
    Index,
    Invoke,
    LocalAssign,
    LocalFunction,
    Name,
    Nil,
    Number,
    Return,
    SemiColon,
    String,
    Table,
    TrueExpr,
    AnonymousFunction,
    UnaryOp,
    While,
)
from app.generators.hardcode import inject_hardcode_noise
from app.generators.crypto_backend import chacha20_xor, hkdf_sha256, hmac_sha256
from app.generators.lua_crypto_runtime import LUA_CRYPTO_RUNTIME


class BytecodeUnsupported(ValueError):
    pass


def _body_nodes(block):
    body = getattr(block, 'body', [])
    return body if isinstance(body, list) else getattr(body, 'body', [])


class Compiler:
    def __init__(self, inherited_locals=None):
        self.constants = []
        self.constant_ids = {}
        self.instructions = []
        self.functions = []
        self.blocks = []
        self.loop_breaks = []
        self.allow_block_break = False
        self.locals = dict(inherited_locals or {})

    def declare_local(self, name):
        if name not in self.locals:
            self.locals[name] = f'_r{len(self.locals)}'
        return self.locals[name]

    def ref(self, name):
        return self.locals.get(name, name)

    def const(self, value):
        key = (type(value).__name__, repr(value))
        if key not in self.constant_ids:
            self.constant_ids[key] = len(self.constants)
            self.constants.append(value)
        return self.constant_ids[key]

    def emit(self, op, *args, node=None):
        line = getattr(getattr(node, '_first_token', None), 'line', None)
        self.instructions.append({'op': op, 'args': list(args), 'line': line})
        return len(self.instructions) - 1

    def make_function(self, node):
        child = Compiler(self.locals)
        params = []
        for arg in node.args:
            if isinstance(arg, Name):
                params.append(child.declare_local(arg.id))
        for statement in _body_nodes(node.body):
            child.statement(statement)
        child.emit('RETURN', 0)
        child.emit('HALT')
        function_id = len(self.functions)
        self.functions.append({
            'params': params,
            'program': {'constants': child.constants, 'instructions': child.instructions,
                        'functions': child.functions, 'blocks': child.blocks}
        })
        return function_id

    def make_block(self, body, targets):
        child = Compiler(self.locals)
        child.allow_block_break = True
        params = []
        for target in targets:
            if isinstance(target, Name):
                params.append(child.declare_local(target.id))
        for statement in _body_nodes(body):
            child.statement(statement)
        child.emit('HALT')
        block_id = len(self.blocks)
        self.blocks.append({
            'params': params,
            'program': {'constants': child.constants, 'instructions': child.instructions,
                        'functions': child.functions, 'blocks': child.blocks}
        })
        return block_id

    def expression(self, node):
        if isinstance(node, Name):
            self.emit('LOAD_NAME', self.ref(node.id), node=node)
        elif isinstance(node, Index):
            self.expression(node.value)
            self.expression(node.idx)
            self.emit('GET_INDEX', node=node)
        elif isinstance(node, String):
            value = node.s.decode('utf-8', errors='replace') if isinstance(node.s, bytes) else node.s
            self.emit('CONST', self.const(value), node=node)
        elif isinstance(node, Number):
            self.emit('CONST', self.const(node.n), node=node)
        elif isinstance(node, (TrueExpr, FalseExpr)):
            self.emit('CONST', self.const(bool(node.value)), node=node)
        elif isinstance(node, Nil):
            self.emit('CONST', self.const(None), node=node)
        elif isinstance(node, Table):
            self.emit('TABLE_NEW', node=node)
            next_index = 1
            for field in node.fields:
                if not isinstance(field, Field):
                    raise BytecodeUnsupported(f'Campo de tabela não suportado: {type(field).__name__}')
                if field.key is None:
                    self.emit('CONST', self.const(next_index), node=field)
                    next_index += 1
                elif isinstance(field.key, Name):
                    self.emit('CONST', self.const(field.key.id), node=field)
                else:
                    self.expression(field.key)
                self.expression(field.value)
                self.emit('TABLE_SET', node=field)
        elif isinstance(node, AnonymousFunction):
            self.emit('MAKE_FUNCTION', self.make_function(node), node=node)
        elif isinstance(node, BinaryOp):
            self.expression(node.left)
            self.expression(node.right)
            self.emit('BINARY', type(node).__name__, node=node)
        elif isinstance(node, UnaryOp):
            self.expression(node.operand)
            self.emit('UNARY', type(node).__name__, node=node)
        elif isinstance(node, Call):
            self.expression(node.func)
            for arg in node.args:
                self.expression(arg)
            self.emit('CALL', len(node.args), node=node)
        elif isinstance(node, Invoke):
            self.expression(node.source)
            for arg in node.args:
                self.expression(arg)
            method = node.func.id if isinstance(node.func, Name) else None
            if not method:
                raise BytecodeUnsupported('Método Lua sem nome simples não suportado.')
            self.emit('INVOKE', method, len(node.args), node=node)
        else:
            raise BytecodeUnsupported(
                f'Expressão Lua ainda não suportada: {type(node).__name__}'
            )

    def statement(self, node):
        if isinstance(node, SemiColon):
            return
        if isinstance(node, Break):
            if not self.loop_breaks:
                if self.allow_block_break:
                    self.emit('BREAK', node=node)
                    return
                raise BytecodeUnsupported('break fora de um ciclo.')
            self.loop_breaks[-1].append(self.emit('JUMP', None, node=node))
            return
        if isinstance(node, LocalAssign):
            if len(node.targets) != len(node.values):
                if len(node.values) > len(node.targets):
                    raise BytecodeUnsupported(f'Atribuição múltipla incompatível: {len(node.targets)} alvo(s), {len(node.values)} valor(es).')
                node.values = list(node.values) + [None] * (len(node.targets) - len(node.values))
            for value in node.values:
                if value is None:
                    self.emit('CONST', self.const(None), node=node)
                else:
                    self.expression(value)
            for target in reversed(node.targets):
                if not isinstance(target, Name):
                    raise BytecodeUnsupported('Alvo de variável local não suportado.')
                self.emit('STORE_LOCAL', self.declare_local(target.id), node=node)
        elif isinstance(node, (Function, LocalFunction)):
            if isinstance(node.name, Name) and isinstance(node, LocalFunction):
                self.declare_local(node.name.id)
            function_id = self.make_function(node)
            if isinstance(node.name, Name):
                local_name = self.declare_local(node.name.id) if isinstance(node, LocalFunction) else node.name.id
                self.emit('MAKE_FUNCTION', function_id, node=node)
                self.emit('STORE_LOCAL' if isinstance(node, LocalFunction) else 'STORE_NAME', local_name, node=node)
            elif isinstance(node.name, Index):
                self.expression(node.name.value)
                self.expression(node.name.idx)
                self.emit('MAKE_FUNCTION', function_id, node=node)
                self.emit('SET_INDEX', node=node)
            else:
                raise BytecodeUnsupported('Nome de função indexado não suportado.')
        elif isinstance(node, Forin):
            if len(node.iter) != 1 or not isinstance(node.iter[0], Call):
                raise BytecodeUnsupported('Forin precisa de pairs(...) ou ipairs(...).')
            iterator_call = node.iter[0]
            if not isinstance(iterator_call.func, Name) or iterator_call.func.id not in {'pairs', 'ipairs'} or len(iterator_call.args) != 1:
                raise BytecodeUnsupported('Forin suporta apenas pairs(tabela) e ipairs(tabela).')
            self.expression(iterator_call.args[0])
            block_id = self.make_block(node.body, node.targets)
            self.emit('FOR_EACH', block_id, iterator_call.func.id, node=node)
        elif isinstance(node, Fornum):
            if not isinstance(node.target, Name):
                raise BytecodeUnsupported('Fornum precisa de uma variável simples.')
            self.expression(node.start)
            self.expression(node.stop)
            if isinstance(node.step, (int, float, str)):
                self.emit('CONST', self.const(float(node.step)), node=node)
            else:
                self.expression(node.step)
            block_id = self.make_block(node.body, [node.target])
            self.emit('FOR_NUM', block_id, node=node)
        elif type(node).__name__ == 'If':
            self.expression(node.test)
            false_jump = self.emit('JUMP_IF_FALSE', None, node=node)
            for statement in _body_nodes(node.body):
                self.statement(statement)
            if node.orelse:
                end_jump = self.emit('JUMP', None, node=node)
                self.instructions[false_jump]['args'][0] = len(self.instructions)
                for statement in _body_nodes(node.orelse):
                    self.statement(statement)
                self.instructions[end_jump]['args'][0] = len(self.instructions)
            else:
                self.instructions[false_jump]['args'][0] = len(self.instructions)
        elif isinstance(node, Assign):
            if len(node.targets) != len(node.values):
                raise BytecodeUnsupported('Atribuições múltiplas ainda não suportadas.')
            for target, value in zip(node.targets, node.values):
                if isinstance(target, Index):
                    self.expression(target.value)
                    self.expression(target.idx)
                    self.expression(value)
                    self.emit('SET_INDEX', node=node)
                    continue
                if isinstance(target, Name):
                    self.expression(value)
                    self.emit('STORE_LOCAL' if target.id in self.locals else 'STORE_NAME', self.ref(target.id), node=node)
                else:
                    raise BytecodeUnsupported('Alvo de atribuição não suportado.')
        elif isinstance(node, (Call, Invoke)):
            self.expression(node)
            self.emit('POP', node=node)
        elif isinstance(node, While):
            start = len(self.instructions)
            self.expression(node.test)
            false_jump = self.emit('JUMP_IF_FALSE', None, node=node)
            breaks = []
            self.loop_breaks.append(breaks)
            for statement in _body_nodes(node.body):
                self.statement(statement)
            self.loop_breaks.pop()
            self.emit('JUMP', start, node=node)
            end = len(self.instructions)
            self.instructions[false_jump]['args'][0] = end
            for jump in breaks:
                self.instructions[jump]['args'][0] = end
        elif isinstance(node, Return):
            for value in node.values or []:
                self.expression(value)
            self.emit('RETURN', len(node.values or []), node=node)
        else:
            raise BytecodeUnsupported(
                f'Instrução Lua ainda não suportada: {type(node).__name__}'
            )

    def compile(self, tree):
        for node in _body_nodes(tree.body):
            self.statement(node)
        self.emit('HALT')
        return {'constants': self.constants, 'instructions': self.instructions, 'functions': self.functions, 'blocks': self.blocks}


def _lua(value):
    if value is None:
        return 'nil'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '{' + ','.join(_lua(item) for item in value) + '}'
    if isinstance(value, dict):
        return '{' + ','.join('[' + _lua(str(key)) + ']=' + _lua(item) for key, item in value.items()) + '}'
    raise TypeError(f'Valor não serializável para Lua: {type(value).__name__}')


_OP_NAMES = ('CONST', 'LOAD_NAME', 'STORE_LOCAL', 'STORE_NAME', 'TABLE_NEW',
             'TABLE_SET', 'GET_INDEX', 'SET_INDEX', 'BINARY', 'UNARY',
             'MAKE_FUNCTION', 'FOR_EACH', 'FOR_NUM', 'CALL', 'INVOKE',
             'POP', 'BREAK', 'JUMP_IF_FALSE', 'JUMP', 'RETURN', 'HALT')


def _constant_nonce(salt, index):
    return hashlib.sha256(b'RS-HC1' + salt + index.to_bytes(4, 'little')).digest()[:12]


def _protect_constants(constants, key, salt):
    material = hkdf_sha256(key, salt, b'ResourceStudio Hardcode v1', 64)
    encryption_key, mac_key = material[:32], material[32:]
    protected = []
    for index, value in enumerate(constants):
        if isinstance(value, str):
            raw = value.encode('utf-8')
            nonce = _constant_nonce(salt, index)
            encrypted = chacha20_xor(encryption_key, nonce, raw)
            tag = hmac_sha256(mac_key, b'RS-HC1' + salt + nonce + encrypted)
            protected.append({'t': 's', 'v': base64.b64encode(encrypted).decode('ascii'),
                              'n': base64.b64encode(nonce).decode('ascii'),
                              'm': base64.b64encode(tag).decode('ascii')})
        elif value is None:
            protected.append({'t': 'nil'})
        elif isinstance(value, bool):
            protected.append({'t': 'b', 'v': value})
        else:
            protected.append({'t': 'n', 'v': value})
    return protected


def _encode_program(program, opcodes, key, fields=None, salt=None, seal_code=False):
    if fields is None:
        fields = {name: 'h' + secrets.token_hex(3) for name in ('params', 'constants', 'code', 'entry', 'functions', 'blocks', 'salt', 'tag', 'code_nonce')}
    salt = salt or secrets.token_bytes(16)
    constants = list(program.get('constants', []))
    constant_ids = {(type(value).__name__, repr(value)): index for index, value in enumerate(constants)}

    def text_ref(value):
        marker = (type(value).__name__, repr(value))
        index = constant_ids.get(marker)
        if index is None:
            index = len(constants)
            constants.append(value)
            constant_ids[marker] = index
        return {'$': index}

    def encode_arg(value):
        return text_ref(value) if isinstance(value, str) else value

    instructions = [{'op': opcodes[item['op']], 'args': [encode_arg(value) for value in item.get('args', [])]}
                    for item in program.get('instructions', [])]
    packed, entry = _pack_instructions(
        instructions, {opcodes['JUMP'], opcodes['JUMP_IF_FALSE']}
    )
    material = hkdf_sha256(key, salt, b'ResourceStudio Hardcode v1', 64)
    encryption_key, mac_key = material[:32], material[32:]
    code_nonce = secrets.token_bytes(12) if seal_code else b''
    stored_code = chacha20_xor(encryption_key, code_nonce, packed) if seal_code else packed
    code_tag = hmac_sha256(mac_key, b'RS-HC1' + salt + code_nonce + stored_code)
    return {
        fields['constants']: _protect_constants(constants, key, salt),
        fields['code']: base64.b64encode(stored_code).decode('ascii'),
        fields['tag']: base64.b64encode(code_tag).decode('ascii'),
        fields['code_nonce']: base64.b64encode(code_nonce).decode('ascii') if seal_code else None,
        fields['entry']: entry,
        fields['salt']: base64.b64encode(salt).decode('ascii'),
        fields['functions']: [{fields['params']: item.get('params', []),
                       'program': _encode_program(item['program'], opcodes, key, fields, salt, seal_code)}
                      for item in program.get('functions', [])],
        fields['blocks']: [{fields['params']: item.get('params', []),
                    'program': _encode_program(item['program'], opcodes, key, fields, salt, seal_code)}
                   for item in program.get('blocks', [])],
        fields['params']: program.get('params', []),
    }


def _pack_instructions(instructions, jump_ops):
    """Empacota instruções numa ordem física diferente da ordem lógica."""
    order = list(range(len(instructions)))
    secrets.SystemRandom().shuffle(order)
    offsets = {}
    cursor = 1
    for logical_index in order:
        offsets[logical_index] = cursor
        cursor += 2 + len(instructions[logical_index]['args']) * 5 + 4
    output = bytearray()
    for physical_index, logical_index in enumerate(order):
        instruction = instructions[logical_index]
        output.append(instruction['op'] & 0xff)
        args = instruction['args']
        output.append(len(args) & 0xff)
        for position, value in enumerate(args):
            if isinstance(value, dict) and '$' in value:
                output.append(1)
                number = int(value['$'])
            else:
                output.append(0)
                number = int(value)
            if instruction['op'] in jump_ops and position == 0:
                number = offsets.get(number, cursor)
            output.extend(number.to_bytes(4, 'little', signed=False))
        next_logical = logical_index + 1
        next_offset = offsets.get(next_logical, 0)
        output.extend(next_offset.to_bytes(4, 'little', signed=False))
    return bytes(output), offsets.get(0, 1)


_VM_RUNTIME = r'''-- ResourceStudio Bytecode VM v1
local RS_PROGRAM = %s
local program = RS_PROGRAM
local RS_CONVAR_NAME = %s
local RS_ENV = _ENV or _G
local RS_SECRET = RS_ENV.GetConvar and RS_ENV.GetConvar(RS_CONVAR_NAME, '')
    or (RS_ENV.os and RS_ENV.os.getenv and RS_ENV.os.getenv(RS_CONVAR_NAME))
    or ''
local RS_CRYPTO = (function()
%s
end)()
local RS_BREAK = {}
local RS_TYPE, RS_TOSTRING, RS_BYTE, RS_CONCAT = type, tostring, string.byte, table.concat
local RS_UNPACK, RS_SETMETA, RS_TABLE_UNPACK = string.unpack, setmetatable, table.unpack
local RS_PAIRS, RS_IPAIRS = pairs, ipairs
local RS_GC = collectgarbage
local function rs_guard()
    return RS_ENV.type == RS_TYPE and RS_ENV.tostring == RS_TOSTRING
        and RS_ENV.string and RS_ENV.string.byte == RS_BYTE
        and RS_ENV.string.unpack == RS_UNPACK
        and RS_ENV.table and RS_ENV.table.concat == RS_CONCAT
        and RS_ENV.table.unpack == RS_TABLE_UNPACK
        and RS_ENV.setmetatable == RS_SETMETA
        and RS_ENV.pairs == RS_PAIRS and RS_ENV.ipairs == RS_IPAIRS
end

local function rs_decode(value)
    local alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    value = value:gsub('[^'..alphabet..'=]', '')
    return (value:gsub('.', function(x)
        if x == '=' then return '' end
        local r, f = '', (alphabet:find(x) - 1)
        for i = 6, 1, -1 do r = r .. (f %% 2^i - f %% 2^(i-1) > 0 and '1' or '0') end
        return r
    end):gsub('%%d%%d%%d?%%d?%%d?%%d?%%d?%%d?', function(x)
        if #x ~= 8 then return '' end
        local c = 0
        for i = 1, 8 do c = c + (x:sub(i,i) == '1' and 2^(8-i) or 0) end
        return string.char(c)
    end))
end

local RS_SALT = rs_decode(program.salt or '')
local RS_KEY_MATERIAL = RS_CRYPTO.hkdf(RS_SECRET, RS_SALT, 'ResourceStudio Hardcode v1', 64)
local RS_ENC_KEY, RS_MAC_KEY = RS_KEY_MATERIAL:sub(1,32), RS_KEY_MATERIAL:sub(33,64)

local function rs_const(item)
    if item.t == 's' then
        local encrypted = rs_decode(item.v)
        local nonce = rs_decode(item.n)
        local tag = rs_decode(item.m or '')
        local expected = RS_CRYPTO.hmac(RS_MAC_KEY, 'RS-HC1'..RS_SALT..nonce..encrypted)
        if not RS_CRYPTO.equal(expected, tag) then error('ResourceStudio VM: constante alterada') end
        return RS_CRYPTO.chacha(RS_ENC_KEY, nonce, encrypted)
    end
    if item.t == 'nil' then return nil end
    return item.v
end

local function rs_arg(program, value)
    if type(value) == 'table' and value['$'] ~= nil then
        return rs_const(program.constants[value['$'] + 1])
    end
    return value
end

local function rs_exec(program, arguments, parent)
    local stack, locals = {}, {}
    setmetatable(locals, { __index = parent })
    for i, name in ipairs(program.params or {}) do locals[name] = arguments[i] end
    local function push(value) stack[#stack + 1] = value end
    local function pop() local n = #stack; local value = stack[n]; stack[n] = nil; return value end
    local function binary(operator, left, right)
        if operator == 'AddOp' then return left + right end
        if operator == 'SubOp' then return left - right end
        if operator == 'MultOp' then return left * right end
        if operator == 'FloatDivOp' or operator == 'FloorDivOp' then return left / right end
        if operator == 'ModOp' then return left %% right end
        if operator == 'ExpoOp' then return left ^ right end
        if operator == 'Concat' then return left .. right end
        if operator == 'EqToOp' then return left == right end
        if operator == 'NotEqToOp' then return left ~= right end
        if operator == 'GreaterThanOp' then return left > right end
        if operator == 'GreaterOrEqThanOp' then return left >= right end
        if operator == 'LessThanOp' then return left < right end
        if operator == 'LessOrEqThanOp' then return left <= right end
        if operator == 'AndLoOp' then return left and right end
        if operator == 'OrLoOp' then return left or right end
        error('ResourceStudio VM: operador não suportado '..tostring(operator))
    end
    local code = rs_decode(program.code or '')
        local code_nonce = program.code_nonce and rs_decode(program.code_nonce) or ''
        local code_tag = rs_decode(program.tag or '')
        local expected_code_tag = RS_CRYPTO.hmac(RS_MAC_KEY, 'RS-HC1'..RS_SALT..code_nonce..code)
        if not RS_CRYPTO.equal(expected_code_tag, code_tag) then error('ResourceStudio VM: bytecode alterado') end
        if #code_nonce > 0 then code = RS_CRYPTO.chacha(RS_ENC_KEY, code_nonce, code) end
        -- O buffer decifrado passa a viver apenas na variável local desta execução.
        -- Lua não garante apagamento físico de strings; isto apenas reduz referências.
        program.code = nil
        program.tag = nil
    local ip = program.entry or 1
    while ip <= #code do
        local op, argc = RS_BYTE(code, ip), RS_BYTE(code, ip + 1)
        ip = ip + 2
        local args = {}
        for i = 1, argc do
            local kind = RS_BYTE(code, ip)
            local value
            value, ip = RS_UNPACK('<I4', code, ip + 1)
            args[i] = kind == 1 and {['$'] = value} or value
        end
        local next_ip
        next_ip, ip = string.unpack('<I4', code, ip)
        local jumped = false
        if op == OP_CONST then push(rs_const(program.constants[args[1] + 1]))
        elseif op == OP_LOAD_NAME then local name = rs_arg(program, args[1]); local value = locals[name]; if value == nil then value = RS_ENV[name] end; push(value)
        elseif op == OP_STORE_LOCAL then locals[rs_arg(program, args[1])] = pop()
        elseif op == OP_STORE_NAME then RS_ENV[rs_arg(program, args[1])] = pop()
        elseif op == OP_TABLE_NEW then push({})
        elseif op == OP_TABLE_SET then local value, key, table_value = pop(), pop(), pop(); table_value[key] = value; push(table_value)
        elseif op == OP_GET_INDEX then local key, table_value = pop(), pop(); push(table_value[key])
        elseif op == OP_SET_INDEX then local value, key, table_value = pop(), pop(), pop(); table_value[key] = value
        elseif op == OP_BINARY then local right, left = pop(), pop(); push(binary(rs_arg(program, args[1]), left, right))
        elseif op == OP_UNARY then local value = pop(); if rs_arg(program, args[1]) == 'ULNotOp' then push(not value) else error('ResourceStudio VM: unário não suportado') end
        elseif op == OP_MAKE_FUNCTION then
            local definition = program.functions[args[1] + 1]
            push(function(...) return rs_exec(definition.program, {...}, locals) end)
        elseif op == OP_FOR_EACH then
            local collection = pop()
            local definition = program.blocks[args[1] + 1]
            local iterator = rs_arg(program, args[2]) == 'ipairs' and RS_IPAIRS or RS_PAIRS
            for key, value in iterator(collection) do
                if rs_exec(definition.program, {key, value}, locals) == RS_BREAK then break end
            end
        elseif op == OP_FOR_NUM then
            local step, stop, start = pop(), pop(), pop()
            local definition = program.blocks[args[1] + 1]
            for value = start, stop, step do
                if rs_exec(definition.program, {value}, locals) == RS_BREAK then break end
            end
        elseif op == OP_CALL then
            local count, call_args = args[1], {}
            for i = count, 1, -1 do call_args[i] = pop() end
            local fn = pop(); if type(fn) ~= 'function' then error('ResourceStudio VM: chamada inválida') end
            push(fn(table.unpack(call_args)))
        elseif op == OP_INVOKE then
            local count, call_args = args[2], {}
            for i = count, 1, -1 do call_args[i] = pop() end
            local object = pop(); local fn = object[rs_arg(program, args[1])]
            if type(fn) ~= 'function' then error('ResourceStudio VM: método inválido '..tostring(rs_arg(program, args[1]))) end
            table.insert(call_args, 1, object)
            push(fn(table.unpack(call_args)))
        elseif op == OP_POP then pop()
        elseif op == OP_BREAK then return RS_BREAK
        elseif op == OP_JUMP_IF_FALSE then if not pop() then ip = args[1]; jumped = true end
        elseif op == OP_JUMP then ip = args[1]; jumped = true
        elseif op == OP_RETURN then
            local count, values = args[1], {}
            for i = count, 1, -1 do values[i] = pop() end
            return table.unpack(values)
        elseif op == OP_HALT then return
        else error('ResourceStudio VM: opcode não suportado '..tostring(op)) end
        if not jumped then ip = next_ip end
    end
end

if RS_SECRET == '' then
    print('[ResourceStudio] VM bloqueada: chave externa ausente.')
    return
end
if not rs_guard() then
    print('[ResourceStudio] VM bloqueada: primitivas Lua alteradas.')
    return
end
return rs_exec(RS_PROGRAM, {}, {})
'''


def _wrap_runtime(runtime):
    """Entrega apenas um loader curto; o interpretador fica cifrado no ficheiro."""
    key = secrets.token_bytes(24)
    encrypted = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(runtime.encode('utf-8')))
    encoded = base64.b64encode(encrypted).decode('ascii')
    chunks, cursor = [], 0
    while cursor < len(encoded):
        size = 29 + secrets.randbelow(43)
        chunks.append(encoded[cursor:cursor + size])
        cursor += size
    order = list(range(len(chunks)))
    # O loader mantém a ordem dos fragmentos; a mutação principal já ocorre nos opcodes.
    parts = ','.join(repr(chunks[index]) for index in order)
    key_payload = base64.b64encode(key).decode('ascii')
    return '''local a={%s};local k=%r;local function d(v)local b='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';v=v:gsub('[^'..b..'=]','');return(v:gsub('.',function(x)if x=='='then return''end;local r,f='',(b:find(x)-1);for i=6,1,-1 do r=r..(f%%2^i-f%%2^(i-1)>0 and'1'or'0')end;return r end):gsub('%%d%%d%%d?%%d?%%d?%%d?%%d?',function(x)if#x~=8 then return''end;local c=0;for i=1,8 do c=c+(x:sub(i,i)=='1'and 2^(8-i)or 0)end;return string.char(c)end))end;local e=d(table.concat(a));local q=d(k);local p={};for i=1,#e do p[i]=string.char(string.byte(e,i)~string.byte(q,((i-1)%%#q)+1))end;return assert(load(table.concat(p),'@ResourceStudioVM'))()''' % (parts, key_payload)


def _secret_name(root, prefix='rs_secret'):
    resource = re.sub(r'[^a-zA-Z0-9_]+', '_', root.name).strip('_').lower() or 'resource'
    return f'{prefix}_{resource}'


def _find_cfg_dir(root):
    for candidate in (root, *root.parents):
        if (candidate / 'server.cfg').is_file():
            return candidate
    return root


def _write_secret_files(root, convar, secret, generic=False):
    cfg_dir = _find_cfg_dir(root)
    cfg_path = cfg_dir / ('hardcode_secrets.env' if generic else 'resource_secrets.cfg')
    line = f'{convar}={secret}' if generic else f'set {convar} "{secret}"'
    existing = cfg_path.read_text(encoding='utf-8', errors='replace').splitlines() if cfg_path.is_file() else []
    replaced = False
    output = []
    for item in existing:
        pattern = rf'^\s*{re.escape(convar)}=' if generic else rf'^\s*set\s+{re.escape(convar)}\s+'
        if re.match(pattern, item, re.IGNORECASE):
            output.append(line)
            replaced = True
        else:
            output.append(item)
    if not replaced:
        output.append(line)
    cfg_path.write_text('\n'.join(output).rstrip() + '\n', encoding='utf-8')
    readme = cfg_dir / ('hardcode_secrets.README.md' if generic else 'resource_secrets.README.md')
    readme.write_text(
        '# ResourceStudio — chaves externas\n\n'
        'No `server.cfg`, adiciona:\n\n'
        '```cfg\nexec resource_secrets.cfg\n```\n\n'
        'O ficheiro `resource_secrets.cfg` deve permanecer fora do recurso e nunca deve ser partilhado.\n'
        'Cada recurso protegido usa uma variável `set` própria.\n',
        encoding='utf-8'
    )
    if generic:
        readme.write_text(
            '# ResourceStudio — Hardcode\n\n'
            'Este modo não depende do FiveM. Define a variável antes de iniciar o Lua:\n\n'
            '```powershell\n$env:' + convar + '="SEGREDO_DO_PROJETO"\n```\n\n'
            'O ficheiro `hardcode_secrets.env` contém o valor gerado e deve permanecer privado.\n',
            encoding='utf-8'
        )
    return str(cfg_path), str(readme), line


def _compact_lua(source):
    """Remove comentários e quebras fora de strings sem alterar literais Lua."""
    output, quote, escaped, comment = [], None, False, False
    pending_space = False
    for char in source:
        if comment:
            if char == '\n':
                comment = False
                pending_space = True
            continue
        if quote:
            output.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"":
            if pending_space and output and output[-1] not in ' ({[,;':
                output.append(' ')
            pending_space = False
            quote = char
            output.append(char)
        elif char == '-' and output and output[-1] == '-':
            output.pop()
            comment = True
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and output and output[-1] not in ' ({[,;':
                output.append(' ')
            pending_space = False
            output.append(char)
    return ''.join(output).strip()


def render_vm(program, convar, secret, seal_code=False):
    program = inject_hardcode_noise(program, 5 + secrets.randbelow(6))
    values = list(range(17, 256))
    secrets.SystemRandom().shuffle(values)
    opcodes = dict(zip(_OP_NAMES, values[:len(_OP_NAMES)]))
    key = secret.encode('utf-8')
    fields = {name: 'h' + secrets.token_hex(3) for name in ('params', 'constants', 'code', 'entry', 'functions', 'blocks', 'salt', 'tag', 'code_nonce')}
    salt = secrets.token_bytes(16)
    encoded = _encode_program(program, opcodes, key, fields, salt, seal_code)
    # O runtime entra através de %s; os operadores % internos não devem ser
    # escapados, porque não são interpretados pelo formatador externo.
    crypto_runtime = LUA_CRYPTO_RUNTIME
    rendered = _VM_RUNTIME % (_lua({fields['params']: [], **encoded}), json.dumps(convar), crypto_runtime)
    for name in ('params', 'constants', 'code_nonce', 'code', 'entry', 'functions', 'blocks', 'salt', 'tag'):
        rendered = rendered.replace('program.' + name, "program['" + fields[name] + "']")
    for name, value in opcodes.items():
        rendered = rendered.replace('OP_' + name, str(value))
    runtime_names = (
        'RS_PROGRAM', 'RS_CONVAR_NAME', 'RS_ENV', 'RS_SECRET', 'RS_BREAK',
        'RS_TYPE', 'RS_TOSTRING', 'RS_BYTE', 'RS_CONCAT', 'rs_guard',
        'rs_decode', 'rs_stream', 'rs_const', 'rs_arg', 'rs_exec',
        'program', 'arguments', 'parent', 'stack', 'locals', 'push', 'pop',
        'binary', 'operator', 'left', 'right', 'value', 'args', 'argc',
        'kind', 'code', 'instruction', 'definition', 'collection', 'iterator',
        'call_args', 'object', 'fn', 'count', 'values', 'encrypted', 'clear',
        'stream', 'suffix', 'state', 'output', 'alphabet', 'number', 'position'
    )
    for name in runtime_names:
        rendered = re.sub(r'\b' + re.escape(name) + r'\b', 'r' + secrets.token_hex(3), rendered)
    # Modo avançado definitivo: o interpretador é executado diretamente.
    # Não reconstruímos o runtime através de load(), evitando o ataque simples
    # que substitui load() por print() para capturar o payload.
    return _compact_lua(rendered)


def compile_lua_bytecode(root_value, source_file, preview=False,
                         output_suffix='_vm', secret_prefix='rs_secret',
                         server_only=True, hardcore=False):
    root = Path(root_value).expanduser().resolve()
    source = (root / str(source_file)).resolve()
    if root not in source.parents or not source.is_file() or source.suffix.lower() != '.lua':
        raise ValueError('O ficheiro Lua selecionado não é válido.')
    relative = source.relative_to(root)
    if server_only and not any(part.lower() == 'server' for part in relative.parts) and source.name.lower() not in {'server.lua', 'main_server.lua'}:
        raise ValueError('A VM com chave externa so pode proteger ficheiros de servidor. Nao uses esta camada em client.lua.')
    text = source.read_text(encoding='utf-8', errors='replace')
    try:
        tree = ast.parse(text)
        program = Compiler().compile(tree)
    except BytecodeUnsupported:
        raise
    except Exception as exc:
        raise ValueError(f'Não foi possível compilar Lua para bytecode: {exc}') from exc
    convar = _secret_name(root, secret_prefix)
    secret = secrets.token_urlsafe(32)
    result = {
        'format': 'resource-studio-bytecode',
        'version': 1,
        'build_id': secrets.token_hex(8),
        'source': str(source),
        'instruction_count': len(program['instructions']),
        'constant_count': len(program['constants']),
        'program': program,
        'secret_convar': convar,
    }
    result['serialized'] = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    result['lua_code'] = render_vm(result['program'], convar, secret, hardcore)
    if not preview:
        target = source.with_name(source.stem + output_suffix + '.lua')
        index = 2
        while target.exists():
            target = source.with_name(f'{source.stem}_vm_{index}.lua')
            index += 1
        target.write_text(result['lua_code'], encoding='utf-8')
        cfg_path, readme_path, config_line = _write_secret_files(root, convar, secret, not server_only)
        result['secret_config_path'] = cfg_path
        result['readme_path'] = readme_path
        result['config_line'] = config_line
        result['path'] = str(target)
    return result
