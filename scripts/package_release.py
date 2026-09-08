"""Package public source files from the working tree without Git history."""

from pathlib import Path
import subprocess
import fnmatch
import sys
import zipfile

from app.config import APP_VERSION, BASE_DIR

PUBLIC_DIRS = {'app', 'bin', 'config', 'deploy', 'docs', 'evals', 'examples', 'knowledge', 'playbooks', 'scripts', 'tests', 'training', '.github'}
PUBLIC_ROOT = {'.gitignore', '.flake8', 'README.md', 'README_TRAINING.md', 'CHANGELOG.md',
               'LICENSE', 'requirements.txt', 'requirements-training.txt', 'deploy.sh',
               'razaai', 'razaai-8g', 'raza-code', 'endpoint-install',
               'train_raza_v3.py', 'train_raza_glm.py', 'merge_glm_gguf.py',
               'eval_glm_checkpoints.py', 'build_v2_dataset.py'}


def ignored_path(name, patterns):
    """Apply this project's path and directory ignore rules in source archives."""
    ignored = False
    for rule in patterns:
        if not rule or rule.startswith('#'):
            continue
        negate = rule.startswith('!')
        pattern = rule.lstrip('!')
        directory = pattern.endswith('/')
        pattern = pattern.rstrip('/')
        parts = name.split('/')
        candidates = ['/'.join(parts[:i]) for i in range(1, len(parts))] if directory else [name]
        if '/' not in pattern:
            candidates = parts[:-1] if directory else parts
        matched = any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates)
        if matched:
            ignored = not negate
    return ignored


def public_files(root=BASE_DIR):
    """Return public working-tree files, or files in an extracted source archive."""
    root = Path(root).resolve()
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=root, capture_output=True)
    patterns = (root / '.gitignore').read_text().splitlines()
    if result.returncode == 0:
        names = set(p.decode() for p in result.stdout.split(b'\0') if p)
    else:
        names = {p.name for p in root.iterdir() if p.is_file()}
        for directory in PUBLIC_DIRS:
            base = root / directory
            if base.is_dir():
                names.update(str(p.relative_to(root)) for p in base.rglob('*') if p.is_file())
    for name in sorted(names):
        path = root / name
        if ignored_path(name, patterns) or not path.is_file() or path.is_symlink():
            continue
        if Path(name).parts[0] in PUBLIC_DIRS or name in PUBLIC_ROOT or name.startswith('Modelfile.'):
            yield path


def main(argv=None):
    out_dir = Path((argv or ['dist'])[0]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'RazaAI-v{APP_VERSION}.zip'
    files = list(public_files())
    for required in ('razaai', 'razaai-8g', 'bin/launch-profile', 'app/launcher.py', 'README.md'):
        if BASE_DIR / required not in files:
            raise RuntimeError(f'Required release file missing: {required}')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(BASE_DIR))
    with zipfile.ZipFile(target) as archive:
        for name in ('razaai', 'razaai-8g', 'bin/launch-profile', 'deploy.sh', 'scripts/package_release.sh'):
            mode = (archive.getinfo(name).external_attr >> 16) & 0o777
            if mode != ((BASE_DIR / name).stat().st_mode & 0o777) or not mode & 0o111:
                target.unlink()
                raise RuntimeError(f'executable mode mismatch: {name}')
    print(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
