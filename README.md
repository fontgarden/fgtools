# fontgarden-tools

Source tools for the Font.Garden font projects. The tools read the UFO
masters of a project, report their mark colors, check glyphs against the
design targets, check source changes before review, lint the outlines,
evaluate drafting methods and list the reviews of drafts from the Git
history. The tools do not change the UFO sources.

The package installs one command, `fgtools`.

The build uses fontc, the Rust compiler of Google Fonts that replaces
fontmake, through `gftools builder`. Quality control of a build uses
diffenator3: `fgtools diff` compares a build with the build of
another revision, and `diff --fontmake` compares fontc with fontmake.

The package was extracted from the scripts of
[Virtua Grotesk](https://github.com/eliheuer/virtua-grotesk), which is the
reference project.

## Install

The package needs Python 3.13 or later. Install it into the virtual
environment of the font project:

```sh
.venv/bin/python -m pip install -e /path/to/fontgarden-tools
.venv/bin/fgtools install-tools
```

`install-tools` installs the pinned fontc and Fontspector release binaries
into the same environment, after a check of their SHA-256 checksums. `build`
and `diff` also need `gftools`, from the requirements of the project.
`check-design` and `check-changes --proof` need the Runebender binary. Set
`RUNEBENDER` to its path if it is not on `PATH`.

## Project layout

A project is a directory that contains `sources/config.yaml`, the gftools
builder configuration. The commands use the current directory or the nearest
parent that contains that file. The tools read these files:

| File | Use |
| --- | --- |
| `sources/config.yaml` | `sources` names the designspace. `outputDir` is the fonts directory. Both are relative to `sources/`. |
| The designspace | The masters are its `<source>` elements, in order. |
| `sources/design.toml` | Grid, stroke targets (`targets`), mark colors (`colors`) and the first date that `corrections` lists (`[corrections] start`). |
| `sources/held-out-glyphs.toml` | The cases of `evaluate-drafting`. |

The name of a master is the `stylename` attribute of its `<source>`. Without
that attribute, it is the part of the UFO file name after the last `-`,
without `.ufo`. For example, `Family-Bold.ufo` gives `Bold`. The first source
is the default master.

Glyph names give the script of a glyph: a name that contains `-ar` is
Arabic, `-hb` is Hebrew, and every other glyph is in the group "Latin and
other". These are the suffixes of the Glyphs naming convention.

`check-changes` and `corrections` read the Git history. The project root must
be the top level of its Git repository.

## Commands

| Command | Use |
| --- | --- |
| `fgtools status [--print]` | Write `STATUS.md` in the project root from the mark colors. `--print` prints it only. |
| `fgtools queue` | Rank the glyphs that most composites wait on. The same as `check-design --queue`. |
| `fgtools check-design GLYPH ...` | Check glyphs against the grid and stroke targets. Also `--not-green`, `--green`, `--ready`, `--observe`, `--json`. |
| `fgtools check-changes [--base REV] [--glyphs "a b"] [--allow-other] [--proof DIR]` | Compare the sources with a base revision (default `main`). Exit status 1 when a green glyph changed or a changed contour glyph is not purple. |
| `fgtools lint-glifs [GLYPH ...]` | Find structural faults in the GLIF files and differences between the masters. |
| `fgtools lint-curves MASTER (GLYPH ... \| --all) [--joins]` | Crest centering, tension breaks, inflections and join continuity in one master. |
| `fgtools evaluate-drafting prepare TASK RUN` | Copy the sources into `RUN/sources` and hide or move the held-out glyphs. `TASK` is `redraw`, `bold`, `repair` or `relatives`. |
| `fgtools evaluate-drafting score RUN` | Score the drafts in `RUN` against the project sources. |
| `fgtools evaluate-drafting compare RUN RUN` | Compare the scores of two runs. |
| `fgtools corrections [--all]` | List the reviews of purple drafts from the Git history. |
| `fgtools build [--compiler fontmake]` | Remove the fonts directory and build the fonts with `gftools builder` and fontc, from a temporary copy of the sources that has one glyph order in all masters. `--compiler fontmake` builds with fontmake. |
| `fgtools diff [--base REV \| --fontmake]` | Build the sources of the working tree and of `REV` (default `main`), or with fontc and fontmake, and compare the builds with diffenator3. HTML reports go to `out/diff/`. Exit status 1 when a glyph or word image differs. |
| `fgtools install-tools` | Install the pinned fontc and Fontspector binaries next to the Python of the environment. |

`fgtools COMMAND --help` lists the arguments of a command. Each command
runs one module, so `python -m fontgarden.status --print` is the same as
`fgtools status --print`.

| Module | Command |
| --- | --- |
| `fontgarden.status` | `status` |
| `fontgarden.check_design` | `check-design`, `queue` |
| `fontgarden.check_changes` | `check-changes` |
| `fontgarden.glif_lint` | `lint-glifs` |
| `fontgarden.curve_lint` | `lint-curves` |
| `fontgarden.evaluate_drafting` | `evaluate-drafting` |
| `fontgarden.list_corrections` | `corrections` |
| `fontgarden.build_source_snapshot` | `build` |
| `fontgarden.diff` | `diff` |
| `fontgarden.install_tools` | `install-tools` |
| `fontgarden.source_inventory` | None. Other modules import it to read glyph records. |
| `fontgarden.project` | None. It finds the project and reads its layout. |

## Tests

```sh
python -m unittest discover -s tests
```

The tests build a small project with two masters in a temporary directory.
To run the project tests on a real project too, set `FONTGARDEN_TEST_PROJECT`
to its root.

## License

Apache License 2.0. See [LICENSE](LICENSE).
