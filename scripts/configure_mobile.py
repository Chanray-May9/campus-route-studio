"""Pin the owner's HTTPS backend and RSA license public key into a mobile build."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument('--backend', required=True)
parser.add_argument('--public-key', required=True)
args = parser.parse_args()
parts = urlsplit(args.backend)
if parts.scheme != 'https' or not parts.hostname or parts.query or parts.fragment or parts.username or parts.path not in ('', '/'):
    parser.error('backend must be an HTTPS origin, e.g. https://your-domain.example')
key = Path(args.public_key).read_text()
if 'BEGIN PUBLIC KEY' not in key:
    parser.error('Expected the backend license-public.pem; never use a private key')
root = Path(__file__).resolve().parent.parent
(root / 'mobile' / 'assets' / 'config.json').write_text(json.dumps({'backend': args.backend.rstrip('/'), 'licensePublicKey': key}), encoding='utf-8')
print('Public configuration saved. Rebuild the APK; private keys stay on the backend.')
