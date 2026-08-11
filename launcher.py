import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.config import WEB, PORT
from app.generators.fivem import inspect_resource, build_manifest, manifest_diagnostics, complete_manifest, detect_lua_files
from app.generators.simple_protection import build_simple
from app.generators.lua_obfuscator import build_lua_obfuscated
from app.support_guard import support_cards_valid


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/health':
            valid = support_cards_valid()
            self.send_json({'ok': valid, 'service': 'ResourceStudio', 'mode': 'local-toolkit', 'support_cards': valid, 'fivem_generator': 'v2'}, 200 if valid else 423)
            return
        if not support_cards_valid():
            self.send_response(423)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            body = '<!doctype html><meta charset="utf-8"><title>ResourceStudio bloqueado</title><style>body{margin:0;background:#07111f;color:#edf5ff;font:16px Segoe UI,Arial;display:grid;place-items:center;min-height:100vh;text-align:center}main{max-width:620px;padding:40px;border:1px solid #ff6b7d66;border-radius:18px;background:#0e1d31}h1{color:#ff8b9a}p{color:#a9bed6}</style><main><h1>ResourceStudio bloqueado</h1><p>Os cards oficiais de apoio foram removidos ou alterados. Restaura a versão original do PayPal e do Discord para continuar.</p></main>'.encode('utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        file = WEB / 'index.html' if path == '/' else WEB / path.lstrip('/')
        if file.is_file() and WEB in file.resolve().parents:
            raw = file.read_bytes()
            kind = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', kind + ('; charset=utf-8' if kind.startswith('text/') or kind == 'application/javascript' else ''))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_json({'error': 'Página não encontrada.'}, 404)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or '{}')
            route = urlparse(self.path).path
            if route not in {'/api/fivem/analyze', '/api/fivem/manifest', '/api/fivem/manifest/check', '/api/fivem/manifest/complete', '/api/lua/analyze', '/api/ipblock/analyze', '/api/security/simple', '/api/security/simple/preview', '/api/obfuscator/preview', '/api/obfuscator/generate', '/api/bytecode/preview'}:
                self.send_json({'error': 'Função não disponível nesta versão.'}, 404)
                return
            if route in {'/api/lua/analyze', '/api/ipblock/analyze'}:
                self.send_json(detect_lua_files(body.get('path', '')))
                return
            if route == '/api/security/simple':
                self.send_json(build_simple(body.get('path', ''), body.get('file', ''), body.get('options', {}), body.get('ip', ''), body.get('server_id', 'local-server'), body.get('days', '30')), 201)
                return
            if route == '/api/security/simple/preview':
                self.send_json(build_simple(body.get('path', ''), body.get('file', ''), body.get('options', {}), body.get('ip', ''), body.get('server_id', 'local-server'), body.get('days', '30'), True))
                return
            if route == '/api/obfuscator/preview':
                if body.get('level') == 'hardcode':
                    from app.generators.hardcode_engine import compile_hardcode
                    result = compile_hardcode(body.get('path', ''), body.get('file', ''), True)
                    result['code'] = result['lua_code']
                    self.send_json(result)
                    return
                if body.get('level') == 'bytecode':
                    from app.generators.lua_bytecode import compile_lua_bytecode
                    result = compile_lua_bytecode(body.get('path', ''), body.get('file', ''), True)
                    result['code'] = result['lua_code']
                    result['level'] = body.get('level')
                    self.send_json(result)
                    return
                self.send_json(build_lua_obfuscated(body.get('path', ''), body.get('file', ''), body.get('level', 'compatibility'), body.get('remove_comments', True), True))
                return
            if route == '/api/obfuscator/generate':
                if body.get('level') == 'hardcode':
                    from app.generators.hardcode_engine import compile_hardcode
                    self.send_json(compile_hardcode(body.get('path', ''), body.get('file', ''), False), 201)
                    return
                if body.get('level') == 'bytecode':
                    from app.generators.lua_bytecode import compile_lua_bytecode
                    result = compile_lua_bytecode(body.get('path', ''), body.get('file', ''), False)
                    self.send_json(result, 201)
                    return
                self.send_json(build_lua_obfuscated(body.get('path', ''), body.get('file', ''), body.get('level', 'compatibility'), body.get('remove_comments', True)), 201)
                return
            if route == '/api/bytecode/preview':
                from app.generators.lua_bytecode import compile_lua_bytecode
                self.send_json(compile_lua_bytecode(body.get('path', ''), body.get('file', ''), True))
                return
            info = inspect_resource(body.get('path', ''))
            if route == '/api/fivem/analyze':
                self.send_json(info)
            elif route == '/api/fivem/manifest':
                self.send_json({'manifest': build_manifest(info, body.get('author', 'ResourceStudio'), body.get('description', 'FiveM resource'), body.get('version', '1.0.0'), body.get('game', 'gta5'))})
            elif route == '/api/fivem/manifest/check':
                if body.get('manifest') is not None:
                    info['existing_manifest'] = str(body.get('manifest') or '')
                self.send_json(manifest_diagnostics(info))
            else:
                before = manifest_diagnostics(info)
                completed = complete_manifest(info)
                after = dict(info)
                after['existing_manifest'] = completed
                self.send_json({'manifest': completed, 'before': before, 'diagnostics': manifest_diagnostics(after)})
        except ValueError as exc:
            self.send_json({'error': str(exc)}, 400)
        except OSError as exc:
            self.send_json({'error': f'Ficheiro ou pasta não encontrado: {getattr(exc, "filename", "caminho indicado")}'}, 404)


if __name__ == '__main__':
    lock_path = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'ResourceStudio' / 'session.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open('a+')
    try:
        import msvcrt
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit('ResourceStudio já está em execução.')
    print(f'ResourceStudio: http://127.0.0.1:{PORT}')
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
