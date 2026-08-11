<div align="center">

# ResourceStudio

### Local toolkit for preparing, analyzing and protecting FiveM/RedM resources

![ResourceStudio](https://images.unsplash.com/photo-1511512578047-dfb367046420?auto=format&fit=crop&w=1600&q=85)

**A private, local-first workspace for resource developers.**

[![Status](https://img.shields.io/badge/status-active-22d3ee?style=for-the-badge)](https://github.com/Rjcferreira/ResourceStudio)
[![Platform](https://img.shields.io/badge/platform-Windows-5377ff?style=for-the-badge)](https://github.com/Rjcferreira/ResourceStudio)
[![License](https://img.shields.io/badge/license-MIT-49e39a?style=for-the-badge)](LICENSE)

</div>

## Overview

ResourceStudio is a local web panel for preparing FiveM and RedM resources without sending project files to an external service. It runs on `127.0.0.1` and keeps the original resource files untouched.

## Features

![Development workspace](https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=1200&q=85)

- **fxmanifest generator** — analyzes resources and identifies missing or unlisted files.
- **Lua protection** — prepares copies with optional IP and license validation.
- **Lua obfuscation** — compatibility, advanced, bytecode experimental and hardcode modes.
- **Local dashboard** — browser interface available at `http://127.0.0.1:8777`.
- **Safe output workflow** — source files are never overwritten automatically.

## Quick start

1. Download or clone the repository.
2. Run `run.bat`.
3. Open `http://127.0.0.1:8777`.
4. Stop the service with `stop.bat`.

The launcher can install the optional parser dependencies into the local `local_deps` directory. Generated dependencies and runtime files are excluded from version control.

## Project structure

```text
ResourceStudio/
├── app/          # Python API and generators
├── web/          # Local dashboard
├── tests/        # Automated tests
├── launcher.py   # Local HTTP server
├── run.bat       # Start the application
└── stop.bat      # Stop the application
```

## Privacy and security

ResourceStudio is designed for local use. Never commit API keys, license secrets, `.env` files, databases or private server data. Always test generated output on a copy of the original resource.

## Current status

The bytecode module is experimental. Validate generated resources in a private test server before production use.

## License

See [LICENSE](LICENSE).
