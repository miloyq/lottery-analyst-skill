"""Copy a standalone skill to an explicit root without overwriting an install."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'lottery-analyst'


def install(destination, source=SOURCE):
    source = source.resolve()
    target = destination.expanduser().resolve() / 'lottery-analyst'
    if target.is_relative_to(source):
        raise ValueError('Destination must be outside the source skill directory')
    if target.exists() or target.is_symlink():
        raise ValueError('Target already exists; refusing overwrite')
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Source contains symlinks; inspect before distributing')
    for name in ('SKILL.md', 'LICENSE', 'scripts/lottery_cli.py'):
        if not (source / name).is_file():
            raise ValueError(f'Missing required distribution file: {name}')
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    hashes = {}
    for p in source.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            relative = p.relative_to(source)
            if p.read_bytes() != (target / relative).read_bytes():
                raise ValueError('Copy verification failed; inspect the target before retrying')
            hashes[relative.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {'skill': 'lottery-analyst', 'verified_files': hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True, help='Verified skill root; ~ is expanded')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.destination), indent=2))
        return 0
    except (OSError, ValueError) as error:
        # OS errors can contain private paths; do not include them in public diagnostics.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({'error': message}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
