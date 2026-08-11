from pathlib import Path
import fnmatch
import re


def _quote(value):
    """Quote a manifest path/value without inventing or normalising files."""
    return "'" + str(value).replace("'", "\\'") + "'"


def _block(name, values):
    values = sorted(dict.fromkeys(values), key=str.lower)
    if not values:
        return []
    lines = [f"{name} {{"]
    lines.extend(f"    {_quote(value)}," for value in values)
    lines += ['}', '']
    return lines


def build_manifest(info, author='ResourceStudio', description='FiveM resource',
                   version='1.0.0', game='gta5'):
    """Build an fxmanifest from the exact files returned by inspect_resource.

    No glob is generated here: every script and asset entry comes from the
    directory snapshot, so the output cannot reference files that do not exist.
    """
    existing = info.get('existing_manifest', '')
    if existing.strip():
        # A hand-written/generated manifest contains semantics that a folder
        # scan cannot safely reconstruct (exports, dependencies, escrow rules,
        # ordering and comments). Preserve it as the source of truth.
        return existing.rstrip() + '\n'

    lines = [
        "fx_version 'cerulean'",
        f"game {_quote(game)}",
        '',
        f"author {_quote(author)}",
        f"description {_quote(description)}",
        f"version {_quote(version)}",
        '',
        "lua54 'yes'",
        '',
    ]

    lua = list(info.get('lua', []))
    client = list(info.get('client', []))
    server = list(info.get('server', []))
    shared = list(info.get('shared', []))
    assigned = set(client) | set(server) | set(shared)
    unassigned_lua = [path for path in lua if path not in assigned]

    lines += _block('shared_scripts', shared)
    lines += _block('client_scripts', client)
    lines += _block('server_scripts', server)
    # Lua outside client/server/shared is still included exactly once.
    lines += _block('shared_scripts', unassigned_lua)

    html = list(info.get('html', []))
    if info.get('nui') and html:
        page = next((x for x in html if Path(x).name.lower() == 'index.html'), html[0])
        lines += [f"ui_page {_quote(page)}", '']

    # FiveM needs web/data/assets exposed through files. Include every actual
    # discovered file except scripts already declared above and fxmanifest.lua.
    declared_scripts = set(client) | set(server) | set(shared)
    all_files = list(info.get('all_files', []))
    if not all_files:
        all_files = list(info.get('files_list', []))
    assets = [
        path for path in all_files
        if path.lower() != 'fxmanifest.lua' and path not in declared_scripts
    ]
    lines += _block('files', assets)
    return '\n'.join(lines).rstrip() + '\n'


def _declared_blocks(manifest):
    blocks = {}
    for name, body in re.findall(r'(?m)^\s*(client_scripts|server_scripts|shared_scripts|files)\s*\{(.*?)\}', manifest, re.S):
        blocks[name] = re.findall(r"['\"]([^'\"]+)['\"]", body)
    page = re.search(r"(?m)^\s*ui_page\s+['\"]([^'\"]+)['\"]", manifest)
    blocks['ui_page'] = [page.group(1)] if page else []
    return blocks


def manifest_diagnostics(info):
    """Compare an existing manifest with the actual directory snapshot."""
    manifest = info.get('existing_manifest', '')
    if not manifest.strip():
        return {'has_manifest': False, 'missing_declared': [], 'unlisted_files': [], 'covered_by_glob': []}
    blocks = _declared_blocks(manifest)
    declared = {value for values in blocks.values() for value in values}
    actual = [p for p in info.get('all_files', []) if p.lower() not in ('fxmanifest.lua', '__resource.lua')]
    external_declared = sorted(
        value for value in declared
        if value.startswith('@') or value.startswith('resource:')
    )
    missing_declared = sorted(
        value for value in declared
        if value not in external_declared
        and not any(ch in value for ch in '*?[')
        and value not in actual
    )
    covered_by_glob = []
    unlisted = []
    for path in actual:
        if path in declared:
            continue
        patterns = [value for value in declared if any(ch in value for ch in '*?[')]
        matched = next((pattern for pattern in patterns if fnmatch.fnmatchcase(path, pattern)), None)
        if matched:
            covered_by_glob.append({'file': path, 'pattern': matched})
        else:
            unlisted.append(path)
    return {
        'has_manifest': True,
        'manifest_path': info.get('manifest_path', 'fxmanifest.lua'),
        'missing_declared': missing_declared,
        'external_declared': external_declared,
        'unlisted_files': sorted(unlisted, key=str.lower),
        'covered_by_glob': sorted(covered_by_glob, key=lambda item: item['file'].lower()),
        'blocks': blocks,
    }


def complete_manifest(info):
    """Safely add only real, currently unlisted files to an existing manifest."""
    existing = info.get('existing_manifest', '')
    if not existing.strip():
        return build_manifest(info)
    diagnostics = manifest_diagnostics(info)
    additions = {'client_scripts': [], 'server_scripts': [], 'shared_scripts': [], 'files': []}
    for path in diagnostics['unlisted_files']:
        low = path.lower()
        if low.endswith('.lua') and (low.startswith('client/') or '/client/' in low):
            additions['client_scripts'].append(path)
        elif low.endswith('.lua') and (low.startswith('server/') or '/server/' in low):
            additions['server_scripts'].append(path)
        elif low.endswith('.lua') and (low.startswith('shared/') or '/shared/' in low):
            additions['shared_scripts'].append(path)
        elif low.endswith('.lua'):
            additions['shared_scripts'].append(path)
        else:
            additions['files'].append(path)
    result = existing.rstrip()
    for block_name, values in additions.items():
        if not values:
            continue
        block = re.search(r'(?m)^(\s*' + re.escape(block_name) + r'\s*\{)(.*?)(^\s*\})', result, re.S)
        if block:
            additions_text = ''.join(f"    {_quote(value)},\n" for value in values)
            result = result[:block.end(2)] + '\n' + additions_text.rstrip('\n') + result[block.end(2):]
        else:
            result += '\n\n' + '\n'.join(_block(block_name, values)).rstrip()
    return result.rstrip() + '\n'
