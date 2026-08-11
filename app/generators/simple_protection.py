from __future__ import annotations
import base64, time
from pathlib import Path

def build_simple(root_value, source_file, options, allowed_ip='', server_id='local-server', duration='30', preview=False):
    root = Path(root_value).expanduser().resolve()
    source = (root / str(source_file)).resolve()
    if root not in source.parents or not source.is_file() or source.suffix.lower() != '.lua':
        raise ValueError('O ficheiro Lua selecionado não é válido.')
    original = source.read_text(encoding='utf-8', errors='replace')
    if 'ResourceStudio Simple Protection v1' in original:
        raise ValueError('Este ficheiro já contém proteção ResourceStudio.')
    ip_enabled = bool(options.get('ip'))
    license_enabled = bool(options.get('license'))
    validity_enabled = license_enabled
    if ip_enabled and not str(allowed_ip).strip(): raise ValueError('Indica o IP autorizado.')
    if validity_enabled and not license_enabled: raise ValueError('A validade precisa da licença ativa.')
    if license_enabled and duration not in {'30','60','90','120','365','lifetime'}: raise ValueError('Validade de licença inválida.')
    project_id = root.name
    now = int(time.time())
    duration = duration if license_enabled else None
    expiry = 0 if not license_enabled or duration == 'lifetime' else now + int(duration) * 86400
    enc = lambda value: base64.b64encode(str(value).encode()).decode()
    guard = f'''-- ResourceStudio Simple Protection v1
-- Ficheiro gerado automaticamente. O ficheiro original permanece intacto.
local RESOURCESTUDIO_ENABLE_IP = {str(ip_enabled).lower()}
local RESOURCESTUDIO_ENABLE_LICENSE = {str(license_enabled).lower()}
local RESOURCESTUDIO_ENABLE_LICENSE_VALIDITY = {str(validity_enabled).lower()}
local RESOURCESTUDIO_IP_B64 = {enc(allowed_ip.strip())!r}
local RESOURCESTUDIO_PROJECT_B64 = {enc(project_id)!r}
local RESOURCESTUDIO_SERVER_B64 = {enc(server_id or 'local-server')!r}
local RESOURCESTUDIO_DURATION_B64 = {enc(duration)!r}
local RESOURCESTUDIO_EXPIRES_AT = {expiry}

local function ResourceStudioDecode(value)
    local alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    value = value:gsub('[^'..alphabet..'=]', '')
    return (value:gsub('.', function(x) if x == '=' then return '' end local r,f='',(alphabet:find(x)-1) for i=6,1,-1 do r=r..(f%2^i-f%2^(i-1)>0 and '1' or '0') end return r end):gsub('%d%d%d?%d?%d?%d?%d?%d?', function(x) if #x~=8 then return '' end local c=0 for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end return string.char(c) end))
end

local function ResourceStudioBlock(reason)
    print('[ResourceStudio] Recurso bloqueado: '..tostring(reason))
    return false
end

local function ResourceStudioCheck()
    if RESOURCESTUDIO_ENABLE_IP then
        local endpoint = GetConvar('endpoint_add_tcp', '')
        local detected = endpoint:match('^([^:]+):%d+$') or endpoint
        if detected == '' or detected == '0.0.0.0' or detected == '*' or detected ~= ResourceStudioDecode(RESOURCESTUDIO_IP_B64) then return ResourceStudioBlock('IP não autorizado') end
    end
    if RESOURCESTUDIO_ENABLE_LICENSE then
        if ResourceStudioDecode(RESOURCESTUDIO_PROJECT_B64) ~= {project_id!r} then return ResourceStudioBlock('projeto inválido') end
        if RESOURCESTUDIO_ENABLE_LICENSE_VALIDITY and RESOURCESTUDIO_EXPIRES_AT ~= 0 and os.time() > RESOURCESTUDIO_EXPIRES_AT then return ResourceStudioBlock('licença expirada') end
    end
    return true
end

if not ResourceStudioCheck() then return end

'''
    target = source.with_name(source.stem + '_protected.lua')
    i = 2
    while target.exists(): target = source.with_name(f'{source.stem}_protected_{i}.lua'); i += 1
    if preview: return {'code':guard + original,'source':str(source),'project_id':project_id}
    target.write_text(guard + original, encoding='utf-8')
    return {'path':str(target),'source':str(source),'project_id':project_id,'server_id':server_id or 'local-server','duration':duration}
