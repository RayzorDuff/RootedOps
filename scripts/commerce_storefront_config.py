"""Change only the Woo transport origin in an existing private worker config."""
import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import tempfile


ORIGINS = ('https://shop-test.danks.store', 'https://danks.store', 'https://dankmushrooms.net')


def update(config, origin='https://dankmushrooms.net'):
    if config.get('woo_origin') not in (None, 'https://shop-test.danks.store',
                                        'https://danks.store', 'https://dankmushrooms.net'):
        raise ValueError('Review the existing Woo origin first')
    if origin not in ORIGINS:
        raise ValueError('Reviewed transport origin required')
    return dict(config, woo_origin=origin)


def update_env(original, origin='https://dankmushrooms.net'):
    if origin not in ORIGINS:
        raise ValueError('Reviewed transport origin required')
    pattern = re.compile(r'^[ \t]*(?:export[ \t]+)?MP_COMMERCE_WOO_ORIGIN[ \t]*=(.*)$', re.M)
    matches = list(pattern.finditer(original))
    if len(matches) > 1:
        raise ValueError('Duplicate Woo origin: review private configuration')
    if matches:
        previous = matches[0].group(1).strip().strip("\"'")
        if previous not in ORIGINS:
            raise ValueError('Review the existing Woo origin first')
        return pattern.sub('MP_COMMERCE_WOO_ORIGIN=' + origin, original)
    return original + ('' if original.endswith('\n') else '\n') + 'MP_COMMERCE_WOO_ORIGIN=' + origin + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--dotenv', action='store_true')
    parser.add_argument('--origin', choices=ORIGINS, default='https://dankmushrooms.net')
    args = parser.parse_args()
    path = args.config.resolve()
    if path.stat().st_mode & 0o077:
        raise ValueError('Private configuration required')
    with path.with_suffix(path.suffix + '.hostname.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = path.read_text()
        replacement = (update_env(original, args.origin) if args.dotenv else
                       json.dumps(update(json.loads(original), args.origin), indent=2) + '\n')
        backup = path.with_suffix(path.suffix + '.before-dankmushrooms-net')
        if not backup.exists():
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    print('Woo transport origin updated. Store identities and activation flags retained.')
