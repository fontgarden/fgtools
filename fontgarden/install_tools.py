#!/usr/bin/env python3
"""Install the pinned fontc and Fontspector binaries next to this Python.

The binaries are the official release archives, checked against the SHA-256
checksums below. Change a version and its checksums in one commit.

    fgtools install-tools
"""
from __future__ import annotations

import argparse
import hashlib
import io
import platform
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

# Tool: version, URL pattern, path in the archive, and per platform the
# release target and the SHA-256 checksum of its archive.
TOOLS = {
    'fontc': {
        'version': '2.0.1',
        'url': 'https://github.com/googlefonts/fontc/releases/download/fontc-v{version}/fontc-{target}.tar.gz',
        'member': 'fontc',
        'targets': {
            ('Darwin', 'arm64'): ('aarch64-apple-darwin',
                                  '7e4876d4ab6fed25fd46d01f456ae9f4d761ad0816f612c933d088d25a67b1d8'),
            ('Linux', 'x86_64'): ('x86_64-unknown-linux-gnu',
                                  '15c3abe31f8885bc5ba150cfaa6d0d826eb2ee00881652eb2ef1ad729cd7e757'),
        },
    },
    'fontspector': {
        'version': '1.9.0',
        'url': 'https://github.com/fonttools/fontspector/releases/download/fontspector-v{version}/fontspector-{version}-{target}.tar.gz',
        'member': 'fontspector-{version}-{target}/fontspector',
        'targets': {
            ('Darwin', 'arm64'): ('aarch64-apple-darwin',
                                  '0d34d5f85ac7a2efe57157c31f454e56a759edf888879b53af50b76bb1d6b617'),
            ('Linux', 'x86_64'): ('x86_64-unknown-linux-gnu',
                                  '0d4a7fbc577f7f99a084dec2a7acc13f64f923cbe44c0e3c5e3d76469786b8e2'),
        },
    },
}


def install(name, destination):
    tool = TOOLS[name]
    key = (platform.system(), platform.machine())
    if key not in tool['targets']:
        sys.exit(f'No pinned {name} release for {key}. Install {name} {tool["version"]} '
                 f'into {destination} yourself.')
    target, checksum = tool['targets'][key]
    values = {'version': tool['version'], 'target': target}
    with urllib.request.urlopen(tool['url'].format(**values), timeout=120) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != checksum:
        sys.exit(f'The {name} archive does not match its checksum.')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        member = tar.getmember(tool['member'].format(**values))
        if not member.isfile():
            sys.exit(f'The {name} archive has no executable at {member.name}.')
        data = tar.extractfile(member).read()
    path = destination / name
    path.write_bytes(data)
    path.chmod(0o755)
    subprocess.run([str(path), '--version'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.parse_args()
    destination = Path(sys.executable).parent
    for name in TOOLS:
        install(name, destination)


if __name__ == '__main__':
    main()
