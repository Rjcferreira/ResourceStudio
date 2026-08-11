from pathlib import Path

IGNORED = {'.git', 'node_modules', '__pycache__'}

def inspect_resource(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('A pasta indicada não existe.')
    files = [p for p in root.rglob('*') if p.is_file() and not any(part in IGNORED for part in p.parts)]
    rel = lambda p: p.relative_to(root).as_posix()
    lua = [rel(p) for p in files if p.suffix.lower() == '.lua']
    js = [rel(p) for p in files if p.suffix.lower() in ('.js', '.ts')]
    html = [rel(p) for p in files if p.suffix.lower() in ('.html', '.htm')]
    css = [rel(p) for p in files if p.suffix.lower() == '.css']
    data = [rel(p) for p in files if p.suffix.lower() in ('.meta', '.xml', '.json')]
    client = [x for x in lua if '/client/' in f'/{x.lower()}' or x.lower().startswith('client/')]
    server = [x for x in lua if '/server/' in f'/{x.lower()}' or x.lower().startswith('server/')]
    shared = [x for x in lua if '/shared/' in f'/{x.lower()}' or x.lower().startswith('shared/')]
    # `files` contains Path objects; convert the relative path before using
    # string operations. This keeps resources without HTML/NUI fully valid.
    nui = bool(html) or any(rel(x).lower().startswith(('html/', 'web/', 'nui/')) for x in files)
    all_files = sorted((rel(p) for p in files), key=str.lower)
    manifest_path = next((p for p in files if p.name.lower() in ('fxmanifest.lua', '__resource.lua')), None)
    existing_manifest = manifest_path.read_text(encoding='utf-8-sig', errors='replace') if manifest_path else ''
    return {'root': str(root), 'files': len(files), 'all_files': all_files,
            'lua': lua, 'js': js, 'html': html, 'css': css, 'data': data,
            'client': client, 'server': server, 'shared': shared, 'nui': nui,
            'manifest_path': rel(manifest_path) if manifest_path else '',
            'existing_manifest': existing_manifest}
