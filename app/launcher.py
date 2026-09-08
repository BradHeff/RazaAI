"""Run a hardware profile without duplicating the application."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .profiles import PROFILES


def configure(profile):
    """Set profile defaults before importing application modules."""
    os.environ['RAZAAI_PROFILE'] = profile.name
    root = Path(os.getenv('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / profile.model
    os.environ.setdefault('RAZAAI_STATE_DIR', str(root))
    if profile.name == 'standard':
        os.environ.setdefault('RAZAAI_SERVER_PORT', str(profile.port))
        os.environ.setdefault('RAZAAI_SERVER_MAX_SESSIONS', str(profile.sessions))
        os.environ.setdefault('RAZAAI_SERVER_TOKEN_FILE', str(root / 'server.token'))


def setup_models(profile, source=None):
    """Create local model tags from public models or an existing fine-tune."""
    from .config import OLLAMA_HOST

    env = dict(os.environ, OLLAMA_HOST=OLLAMA_HOST)
    models = [(profile.model, source or profile.base_model, False),
              (profile.code_model, profile.code_base, True)]
    for tag, base, coding in models:
        if any(c in base for c in '\n\r'):
            raise ValueError('Model source must be a single tag or GGUF path')
        local = Path(base).expanduser()
        if local.is_file():
            base = json.dumps(str(local.resolve()))
        elif subprocess.run(['ollama', 'show', base], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['ollama', 'pull', base], env=env, check=True)
        purpose = ('Propose code changes in the format requested by the application. '
                   'You cannot execute commands or write files. Never claim a test passed without supplied evidence.'
                   if coding else 'Answer clearly and concisely. Never invent tool results or observations.')
        text = (f'FROM {base}\nPARAMETER num_ctx {profile.context}\n'
                f'PARAMETER num_batch {profile.batch}\nPARAMETER temperature {0.2 if coding else 0.6}\n'
                f'SYSTEM """You are RazaAI, created by Brad Heffernan. {purpose}"""\n')
        with tempfile.TemporaryDirectory(prefix='raza-model-') as temp:
            path = Path(temp) / 'Modelfile'
            path.write_text(text, encoding='utf-8')
            subprocess.run(['ollama', 'create', tag, '-f', str(path)], env=env, check=True)
        print(f'Ready: {tag}')


def main(argv=None):
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument('--profile', choices=PROFILES, default='standard')
    selected, _ = selector.parse_known_args(argv)
    profile = PROFILES[selected.profile]
    parser = argparse.ArgumentParser(description='RazaAI terminal assistant for RTX workstations and Jetson 8 GB devices', parents=[selector])
    commands = parser.add_subparsers(dest='command')
    if profile.name == 'standard':
        web = commands.add_parser('web', help='Start the workstation browser interface')
        web.add_argument('--host', default=None)
        web.add_argument('--port', type=int, default=None)
        web.add_argument('--workspace', default=None)
        commands.add_parser('token', help='Print the browser access token')
    chat = commands.add_parser('chat', help='Open the terminal interface (default)')
    mode = chat.add_mutually_exclusive_group()
    mode.add_argument('--classic', action='store_true')
    mode.add_argument('--tui', action='store_true')
    chat.add_argument('--workspace', default=None)
    code = commands.add_parser('code', help='Work on code in the terminal')
    code.add_argument('directory', nargs='?', default='.', help='Project directory; defaults to the current directory')
    code.add_argument('--classic', action='store_true')
    commands.add_parser('learn', help='Review incident learning and refresh the knowledge index')
    commands.add_parser('doctor', help='Check this profile and the device')
    commands.add_parser('config', help='Show effective settings without secrets')
    models = commands.add_parser('models', help='Download and build the profile models')
    models.add_argument('--from', dest='source', help='Existing conversation model tag or local GGUF')
    args = parser.parse_args(argv)
    profile = PROFILES[args.profile]
    configure(profile)
    if args.command == 'models':
        setup_models(profile, args.source)
        return 0
    from . import config
    if args.command == 'config':
        print(json.dumps({'profile': profile.name, 'model': config.OLLAMA_MODEL,
                          'code_model': config.CODE_MODEL, 'context': config.OLLAMA_NUM_CTX,
                          'batch': config.OLLAMA_NUM_BATCH, 'state': str(config.state_dir()),
                          'interface': 'terminal',
                          'web_available': profile.name == 'standard',
                          'port': int(os.environ['RAZAAI_SERVER_PORT']) if profile.name == 'standard' else None}, indent=2))
        return 0
    if args.command == 'learn':
        from scripts.learning_loop import main as learn
        return learn()
    if args.command == 'doctor':
        from .doctor import main as doctor
        return doctor()
    if args.command in (None, 'chat', 'code'):
        from .main import main as chat_main
        options = ['--classic'] if getattr(args, 'classic', False) else []
        if getattr(args, 'tui', False):
            options.append('--tui')
        workspace = args.directory if args.command == 'code' else getattr(args, 'workspace', None)
        if workspace:
            options += ['--workspace', workspace]
        return chat_main(options)
    from .server import resolve_token, serve
    if args.command == 'token':
        print(resolve_token())
        return 0
    print(f'Browser access token: run {profile.model} token in another terminal.')
    serve(host=getattr(args, 'host', None) or os.getenv('RAZAAI_SERVER_HOST', '127.0.0.1'),
          port=getattr(args, 'port', None) or int(os.environ['RAZAAI_SERVER_PORT']),
          workspace_root=getattr(args, 'workspace', None))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'RazaAI: {exc}') from None
