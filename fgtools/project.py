"""Find a font project and read the layout of its sources.

A project is a directory that contains sources/config.yaml, the gftools
builder configuration. The project root is the current directory or the
nearest parent that contains that file.

The masters are the <source> elements of the designspace that config.yaml
names, in designspace order. A project with one master names its UFO in
config.yaml, without a designspace. The name of a master is the `stylename`
attribute of its source. Without that attribute, it is the part of the UFO
file name after the last "-", without ".ufo".
"""
from __future__ import annotations

import functools
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

CONFIG = 'sources/config.yaml'


class ProjectError(LookupError):
    """The project or one of its source files is missing or not valid."""


def find_root(start=None):
    """The nearest directory, from `start` upward, that contains sources/config.yaml."""
    start = Path.cwd() if start is None else Path(start)
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG).is_file():
            return folder
    raise ProjectError(f'No {CONFIG} in {start} or a parent directory')


class Project:
    """The source layout of one font project."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = self.root / 'sources'
        self.config_path = self.root / CONFIG
        if not self.config_path.is_file():
            raise ProjectError(f'No {CONFIG} in {self.root}')
        self.config = yaml.safe_load(self.config_path.read_text()) or {}
        entries = [str(entry) for entry in self.config.get('sources') or []]
        designspaces = [entry for entry in entries if entry.endswith('.designspace')]
        self.designspace = (self.sources / designspaces[0]).resolve() if designspaces else None
        self.ufos = {}
        if self.designspace:
            found = [(source.get('stylename'), (self.designspace.parent / source.get('filename')).resolve())
                     for source in ET.parse(self.designspace).getroot().findall('sources/source')]
        else:
            # A project with one master names its UFO in config.yaml.
            found = [(None, (self.sources / entry).resolve())
                     for entry in entries if entry.endswith('.ufo')]
        for name, path in found:
            name = name or path.stem.rsplit('-', 1)[-1]
            if name in self.ufos:
                raise ProjectError(f'{self.config_path}: two masters are named {name}')
            self.ufos[name] = path
        if not self.ufos:
            raise ProjectError(f'{self.config_path}: `sources` names no designspace or UFO '
                               'with masters')
        self.masters = list(self.ufos)
        self.fonts = (self.sources / self.config.get('outputDir', '../fonts')).resolve()
        self.design_config = self.root / 'CONTEXT.md'
        self.held_out = self.sources / 'held-out-glyphs.toml'

    def ufo(self, master, root=None):
        """The UFO of a master. With `root`, the same relative path under that
        directory, for example a copy of the sources."""
        if root is None:
            return self.ufos[master]
        return Path(root) / self.ufo_relative(master)

    def ufo_relative(self, master):
        """The UFO of a master relative to the project root, with "/" separators."""
        return self.ufos[master].relative_to(self.root).as_posix()

    def design(self):
        """The settings of the project: the `toml` code blocks of CONTEXT.md,
        read as one TOML document."""
        # The other lines become empty lines, so that an error names the
        # line of CONTEXT.md.
        lines, inside = [], False
        for line in self.design_config.read_text().splitlines():
            fence = line.strip().startswith('```')
            lines.append(line if inside and not fence else '')
            if fence:
                inside = not inside and line.strip() == '```toml'
        try:
            return tomllib.loads('\n'.join(lines))
        except tomllib.TOMLDecodeError as error:
            raise ProjectError(f'{self.design_config}: {error}') from None


@functools.cache
def _load(root):
    return Project(root)


def load(root=None):
    """The project at `root`, or the project that contains the current directory."""
    return _load(find_root() if root is None else Path(root).resolve())


def layout(root):
    """The project at `root` if `root` is a project, else the current project.

    A copy of the sources, for example a drafting evaluation run, has the
    layout of the current project but no config.yaml of its own.
    """
    if (Path(root) / CONFIG).is_file():
        return load(root)
    return load()
