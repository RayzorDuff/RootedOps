"""Change only the Woo transport origin in an existing private worker config."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import tempfile


def update(config):
    if config.get('woo_origin') not in (None, 'https://shop-test.danks.store',
                                        'https://danks.store', 'https://dankmushrooms.net'):
        raise ValueError('Review the existing Woo origin first')
    return dict(config, woo_origin='https://dankmushrooms.net')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    path = args.config.resolve()
    if path.stat().st_mode & 0o077:
        raise ValueError('Private configuration required')
    with path.with_suffix(path.suffix + '.hostname.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = path.read_text()
        value = update(json.loads(original))
        backup = path.with_suffix(path.suffix + '.before-dankmushrooms-net')
        if not backup.exists():
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as handle:
                handle.write(original)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
            json.dump(value, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    print('Woo transport origin updated. Store identities and activation flags retained.')
