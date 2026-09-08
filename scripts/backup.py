"""Back up or restore local project data and the two profile state directories."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil

from app.config import BASE_DIR


def copy_directory(source, destination):
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('backup', 'restore'))
    parser.add_argument('directory', nargs='?', type=Path)
    args = parser.parse_args()
    root = (args.directory or Path.home() / 'razaai-backups' / datetime.now().strftime('%Y%m%d-%H%M%S')).expanduser().resolve()
    if root == BASE_DIR or BASE_DIR in root.parents:
        parser.error('Keep backups outside the source checkout')
    state_root = Path(os.getenv('XDG_STATE_HOME', str(Path.home() / '.local/state'))).expanduser()
    for name in ('razaai', 'razaai-8g'):
        source = (state_root / name).resolve()
        if root == source or source in root.parents:
            parser.error('Keep backups outside the profile state directories')
    if args.mode == 'backup':
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        for name in ('data', 'config', 'knowledge'):
            copy_directory(BASE_DIR / name, root / name)
        for name in ('razaai', 'razaai-8g'):
            copy_directory(state_root / name, root / 'state' / name)
        (root / '.raza-backup').write_text('1\n')
        print(f'Backup written to {root}')
    else:
        if args.directory is None or not (root / '.raza-backup').is_file():
            parser.error('Choose a backup created by this script')
        for name in ('data', 'config', 'knowledge'):
            copy_directory(root / name, BASE_DIR / name)
        for name in ('razaai', 'razaai-8g'):
            copy_directory(root / 'state' / name, state_root / name)
        print('Restored files without deleting newer files. Rebuild the knowledge index before use.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
