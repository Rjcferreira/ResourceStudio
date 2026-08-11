from pathlib import Path

def detect_lua_files(root: str) -> dict:
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ValueError('A pasta indicada não existe.')
    files = sorted((p for p in base.rglob('*') if p.is_file() and p.suffix.lower() == '.lua'), key=lambda p: str(p).lower())
    relative = [p.relative_to(base).as_posix() for p in files]
    recommended = next((item for item in relative if Path(item).name.lower() == 'server.lua'), relative[0] if relative else '')
    return {'root':str(base),'files':relative,'recommended':recommended}
