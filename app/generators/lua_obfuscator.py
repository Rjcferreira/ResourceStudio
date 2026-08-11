from __future__ import annotations
from pathlib import Path
import re

def compatibility_warnings(original: str, output: str) -> list[str]:
    warnings=[]
    # Nos modos Base64/Avançado o código original fica preservado no payload
    # e é executado pelo loader; não devemos tratar o wrapper como se fosse o
    # código final da aplicação ao procurar eventos/exports.
    if 'ResourceStudio Lua Protector v1' in output:
        if 'ResourceStudio Simple Protection v1' in original:
            warnings.append('O ficheiro já contém proteção ResourceStudio; foi tratado como código opaco.')
        return warnings
    for marker in ('RegisterNetEvent', 'AddEventHandler', 'RegisterCommand', 'exports(', 'exports.'):
        if marker in original and marker not in output:
            warnings.append(f'Referência pública não encontrada no resultado: {marker}')
    if 'ResourceStudio Simple Protection v1' in original:
        warnings.append('O ficheiro já contém proteção ResourceStudio; foi tratado como código opaco.')
    return warnings
import base64
import secrets

def build_obfuscated_manifest(root, selected_file, output_file):
    original = root / 'fxmanifest.lua'
    if not original.is_file(): return None
    selected = str(selected_file).replace('\\','/')
    output = str(output_file).replace('\\','/')
    lines=[]
    for line in original.read_text(encoding='utf-8', errors='replace').splitlines():
        if selected not in line.replace('\\','/'):
            lines.append(line)
            continue
        cleaned=re.sub(r"['\"]"+re.escape(selected)+r"['\"]\s*,?", '', line)
        if cleaned.strip() and cleaned.strip() not in {'server_script','client_script','shared_script','server_scripts','client_scripts','shared_scripts'}:
            lines.append(cleaned)
    folder = Path(output).parts[0].lower() if Path(output).parts else ''
    directive = 'server_script' if folder == 'server' else 'client_script' if folder == 'client' else 'shared_script'
    content = '\n'.join(lines).rstrip() + f"\n\n-- ResourceStudio Lua Protector\n{directive} '{output}'\n"
    target = root / 'fxmanifest_obfuscated.lua'
    target.write_text(content, encoding='utf-8')
    return {'path':str(target),'removed':selected,'added':output}

def transform_lua(source: str, level: str, remove_comments: bool = True) -> str:
    if not remove_comments:
        return source
    lines=[]
    for line in source.splitlines():
        stripped=line.lstrip()
        if stripped.startswith('--'):
            continue
        lines.append(line.rstrip())
    while lines and not lines[-1]: lines.pop()
    return '\n'.join(lines)+'\n'

def build_lua_obfuscated(root_value, source_file, level='compatibility', remove_comments=True, preview=False):
    root=Path(root_value).expanduser().resolve()
    source=(root/str(source_file)).resolve()
    if root not in source.parents or not source.is_file() or source.suffix.lower()!='.lua':
        raise ValueError('O ficheiro Lua selecionado não é válido.')
    original=source.read_text(encoding='utf-8', errors='replace')
    if 'ResourceStudio Lua Protector v1' in original:
        raise ValueError('Este ficheiro já foi processado pelo Lua Protector.')
    # A limpeza é feita antes de criar o payload. Assim, a opção funciona
    # igualmente nos modos Base64 e Avançado, mantendo o código executável.
    protected_source = transform_lua(original, level, remove_comments)
    if level == 'base64':
        payload = base64.b64encode(protected_source.encode('utf-8')).decode('ascii')
        output = '''-- ResourceStudio Lua Protector v1 · Base64
-- Base64 é apenas codificação, não encriptação.
local ResourceStudioPayload = %r
local function ResourceStudioDecode(value)
    local alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    value = value:gsub('[^'..alphabet..'=]', '')
    return (value:gsub('.', function(x) if x == '=' then return '' end local r,f='',(alphabet:find(x)-1) for i=6,1,-1 do r=r..(f%%2^i-f%%2^(i-1)>0 and '1' or '0') end return r end):gsub('%%d%%d%%d?%%d?%%d?%%d?%%d?%%d?', function(x) if #x~=8 then return '' end local c=0 for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end return string.char(c) end))
end
local ResourceStudioChunk = assert(load(ResourceStudioDecode(ResourceStudioPayload), '@ResourceStudioBase64'))
return ResourceStudioChunk()
''' % payload
    elif level == 'advanced':
        key = secrets.token_bytes(24)
        build_id = secrets.token_hex(8)
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(protected_source.encode('utf-8')))
        encoded_payload = base64.b64encode(encrypted).decode('ascii')
        # Fragmentos e ordem aleatória tornam cada build diferente e evitam
        # que exista um único payload evidente no ficheiro final.
        chunks = []
        cursor = 0
        while cursor < len(encoded_payload):
            size = 17 + secrets.randbelow(31)
            chunks.append(encoded_payload[cursor:cursor + size])
            cursor += size
        shuffled = list(range(len(chunks)))
        secrets.SystemRandom().shuffle(shuffled)
        shuffled_chunks = [chunks[index] for index in shuffled]
        order = [shuffled.index(index) + 1 for index in range(len(chunks))]
        chunk_payload = ', '.join(repr(value) for value in shuffled_chunks)
        order_payload = ', '.join(str(value) for value in order)
        key_payload = base64.b64encode(key).decode('ascii')
        checksum = 2166136261
        for byte in encrypted:
            checksum = ((checksum ^ byte) * 16777619) % 4294967296
        output = '''-- ResourceStudio Lua Protector v1 · Advanced
-- Payload próprio XOR + Base64 com loader local.
local ResourceStudioBuild = %r
local ResourceStudioChunks = {%s}
local ResourceStudioOrder = {%s}
local ResourceStudioKey = %r
local ResourceStudioChecksum = %d
local function ResourceStudioDecode(value)
    local alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    value = value:gsub('[^'..alphabet..'=]', '')
    return (value:gsub('.', function(x) if x == '=' then return '' end local r,f='',(alphabet:find(x)-1) for i=6,1,-1 do r=r..(f%%2^i-f%%2^(i-1)>0 and '1' or '0') end return r end):gsub('%%d%%d%%d?%%d?%%d?%%d?%%d?%%d?', function(x) if #x~=8 then return '' end local c=0 for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end return string.char(c) end))
end
local ResourceStudioEncodedParts = {}
for i=1,#ResourceStudioOrder do ResourceStudioEncodedParts[i] = ResourceStudioChunks[ResourceStudioOrder[i]] end
local ResourceStudioData = ResourceStudioDecode(table.concat(ResourceStudioEncodedParts))
local ResourceStudioSecret = ResourceStudioDecode(ResourceStudioKey)
local ResourceStudioActualChecksum = 2166136261
for i=1,#ResourceStudioData do ResourceStudioActualChecksum = ((ResourceStudioActualChecksum ~ string.byte(ResourceStudioData,i)) * 16777619) %% 4294967296 end
if ResourceStudioActualChecksum ~= ResourceStudioChecksum then
    print('[ResourceStudio] Arranque bloqueado: payload alterado ou corrompido.')
    return
end
local ResourceStudioPlain = {}
for i=1,#ResourceStudioData do ResourceStudioPlain[i] = string.char(string.byte(ResourceStudioData,i) ~ string.byte(ResourceStudioSecret,((i-1) %% #ResourceStudioSecret)+1)) end
local ResourceStudioChunk = assert(load(table.concat(ResourceStudioPlain), '@ResourceStudioAdvanced'))
return ResourceStudioChunk()
''' % (build_id, chunk_payload, order_payload, key_payload, checksum)
        internal_names = {name: 'RS_' + secrets.token_hex(4) for name in ('ResourceStudioBuild','ResourceStudioChunks','ResourceStudioOrder','ResourceStudioKey','ResourceStudioChecksum','ResourceStudioDecode','ResourceStudioEncodedParts','ResourceStudioData','ResourceStudioSecret','ResourceStudioActualChecksum','ResourceStudioPlain','ResourceStudioChunk')}
        for old, new in internal_names.items():
            output = output.replace(old, new)
    else:
        output='-- ResourceStudio Lua Protector v1\n-- Compatibilidade FiveM preservada.\n'+transform_lua(original,level,remove_comments)
        if level == 'balanced':
            output='\n'.join(line for line in output.splitlines() if line.strip())+'\n'
    warnings=compatibility_warnings(original, output)
    if preview: return {'code':output,'source':str(source),'level':level,'warnings':warnings,'build_id':build_id if level == 'advanced' else None}
    target=source.with_name(source.stem+'_obfuscated.lua')
    i=2
    while target.exists(): target=source.with_name(f'{source.stem}_obfuscated_{i}.lua'); i+=1
    target.write_text(output,encoding='utf-8')
    manifest = build_obfuscated_manifest(root, source.relative_to(root).as_posix(), target.relative_to(root).as_posix())
    return {'path':str(target),'source':str(source),'level':level,'manifest':manifest,'warnings':warnings,'build_id':build_id if level == 'advanced' else None}
