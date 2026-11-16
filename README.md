# fontgarden-tools

Source tools for the Font.Garden font projects. The tools read the UFO
masters of a project, report their mark colors, check glyphs against the
design targets, check source changes before review, lint the outlines,
evaluate drafting methods and list the reviews of drafts from the Git
history. `proof-web` shows a build beside reference fonts in a browser.
The tools do not change the UFO sources.

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
| `CONTEXT.md` | The design rules of the font. The tools read its `toml` code blocks as one TOML document: grid, stroke targets (`targets`), the weights that `draft-weights` drafts (`weights`), mark colors (`colors`) and the first date that `corrections` lists (`[corrections] start`). |
| `sources/held-out-glyphs.toml` | The cases of `evaluate-drafting`. |
| `sources/proof-samples.toml` | Optional. The text samples of `proof-web`. |
| `reference-fonts/` | The TTF and OTF files that `proof-web` shows beside the font. Keep the license of each font with it, and keep the folder out of Git. |

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
| `fgtools evaluate-drafting run TASK RUN --harness NAME [--model M] [--max-time S]` | Prepare `RUN`, run an agent harness in it without a person, record its time, exit status and cost, and score it. The harnesses and their permissions are in `fontgarden/harnesses.toml`: Claude Code, Codex and OMP. |
| `fgtools evaluate-drafting table RUN ...` | One line for each run: harness, model, task, overlap, distance, compatible glyphs, time and cost. |
| `fgtools report-grid-levels [--master NAME] [--glyphs "NAMES"]` | Count the points on the 8-unit grid, on the 2-unit grid only, and off both, by script and mark color, with the advances and kerning values off the 8-unit grid. With `--glyphs`, list the points of each named glyph that are off the 8-unit grid. |
| `fgtools check-accents [--master NAME] [--tolerance UNITS] [--all]` | List the accented letters whose mark is not where the other accented letters predict, or not where the anchors of its parts are. See [Accent placement](#accent-placement). |
| `fgtools place-anchors [--set NAME] [--master NAME] [--include-green] [--write]` | Add the `top`, `bottom`, `_top` and `_bottom` anchors that are missing on the base letters and the marks of a set of accented letters. See [Accented letters](#accented-letters). |
| `fgtools build-accented-letters [--set NAME] [--characters TEXT] [--glyphs "NAMES"] [--replace-drafts] [--write]` | Add the accented letters of a set as purple composites, in every master. |
| `fgtools render-accent-proofs [--master NAME] [--glyphs "NAMES"] [--references DIR] [--out DIR]` | Draw each accented letter beside the reference fonts, and measure it against them. |
| `fgtools evaluate-accent-placement [FONT.ttf ...] [--letters]` | Test the accent placement methods on compiled fonts, where the positions of the designer are known. Without fonts, it uses one upright font of each family of the [reference fonts](#reference-fonts). |
| `fgtools fetch-reference-fonts [DIRECTORY] [--family NAME ...]` | Download the shared OFL reference fonts from Google Fonts. With `--project`, get the families that `CONTEXT.md` lists into `reference-fonts/` of the project. |
| `fgtools draft-weights [NAME ...] [--build]` | Draft the masters of more weights, for example Thin and Black, from two masters. Each `[weights.<name>]` table of `CONTEXT.md` names the two masters and gives the vertical stem and the horizontal stroke of each master and of the weight. Each coordinate is calculated on the line through its two values, with one position for x and one for y. The drafts go to `output/weights/` with a designspace of all masters, every drafted glyph is purple, and `sources/` does not change. The report lists the glyphs that are not compatible in the two masters and the glyphs with a contour that turned inside out. `--build` compiles a variable font with fontc. |
| `fgtools corrections [--all]` | List the reviews of purple drafts from the Git history. |
| `fgtools build [--compiler fontmake]` | Remove the fonts directory and build the fonts with `gftools builder` and fontc, from a temporary copy of the sources that has one glyph order in all masters. `--compiler fontmake` builds with fontmake. |
| `fgtools qa [--full \| --package DIR]` | Run Fontspector with the Font.Garden profile (the Google Fonts profile plus the em size, grid, vendor ID and license checks) on the built fonts. Without `--full`, it works offline and leaves out the checks in `[qa.exclude]` of `CONTEXT.md`. Reports go to `output/qa/`. |
| `fgtools diff [--base REV \| --fontmake]` | Build the sources of the working tree and of `REV` (default `main`), or with fontc and fontmake, and compare the builds with diffenator3. HTML reports go to `output/diff/`. Exit status 1 when a glyph or word image differs. |
| `fgtools customize --family NAME --designer NAME --email ADDRESS [--repository URL]` | Rename a project made from the [project template](https://github.com/fontgarden/font-project-template): the family name in the sources, the documents and the file names. |
| `fgtools install-tools` | Install the pinned fontc and Fontspector binaries next to the Python of the environment. |
| `fgtools proof-web [--current \| --snapshot DIR \| --directory DIR] [--port N] [--check]` | Serve the font beside `reference-fonts/` in a browser. See [Web proof](#web-proof). |
| `fgtools proof-web prepare --comparison FILE --output-dir DIR` | Prepare a Before and Candidate snapshot from fixed font files. |
| `fgtools proof-web render-detail --text TEXT --weight N --output FILE` | A DesignBot PNG of one sample in each font of the proof. Needs the `designbot` command. |

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
| `fontgarden.draft_weights` | `draft-weights` |
| `fontgarden.benchmark` | `evaluate-drafting run`, `evaluate-drafting table` |
| `fontgarden.grid_levels` | `report-grid-levels` |
| `fontgarden.accent_placement` | `check-accents`, `evaluate-accent-placement` |
| `fontgarden.accented_letters` | `place-anchors`, `build-accented-letters` |
| `fontgarden.accent_proofs` | `render-accent-proofs` |
| `fontgarden.reference_fonts` | `fetch-reference-fonts` |
| `fontgarden.list_corrections` | `corrections` |
| `fontgarden.build_source_snapshot` | `build` |
| `fontgarden.qa`, `fontgarden.fontspector_plugin` | `qa` |
| `fontgarden.diff` | `diff` |
| `fontgarden.install_tools` | `install-tools` |
| `fontgarden.customize` | `customize` |
| `fontgarden.proof_web` | `proof-web`. The web app is in `fontgarden/proof_web/app/`. |
| `fontgarden.source_inventory` | None. Other modules import it to read glyph records. |
| `fontgarden.project` | None. It finds the project and reads its layout. |

## Accent placement

An accented letter is a composite of a base letter and a mark, for example
`Aacute` = `A` + `acute`. Unicode decomposition gives the parts. The module
predicts the offset of the mark with three methods:

| Method | Uses | Top marks within 0.8% of the em |
| --- | --- | ---: |
| `outlines` | The outlines only: the mark is centered on the top of the base and keeps its drawn height over the x-height or the cap height. | 33% |
| `calibrated` | The outlines, with the constant of each mark from the other letters that use it. | 67% |
| `anchors` | The base anchor and the mark anchor that the other accented letters imply, fitted with medians. | 99% |

The numbers are from `evaluate-accent-placement` on one upright font of each
of the 9 families of the [reference fonts](#reference-fonts), 2162 marks, on
2026-11-14. Each letter
is predicted without itself. The `anchors` method needs another mark on the
same base and another base with the same mark; it predicts 86% of the marks.
Bottom marks (cedilla, ogonek, comma accent) are within 0.8% for 72% of the
marks with the `anchors` method, because an ogonek joins a stroke and is not
centered.

The rules are for Latin letters with one mark. A caron on d, t, l and L is
left out, because it is drawn as an apostrophe beside the letter.

`check-accents` uses the `anchors` method on the masters of the project, with
the `calibrated` method where the first has no prediction. It does not
change the sources. A listed letter is a reason to look: a mark on the stem
of L is correct and is not where the centered marks predict.

## Accented letters

Three commands do the work on accented letters, and a review closes it:

1. `place-anchors` adds the anchors that are missing. An anchor that is in
   the sources is the designer's and does not change. A missing anchor is
   fitted to the accented letters that are in the sources (the `anchors`
   method), or comes from the outline for a glyph that no accented letter
   uses. Purple and red accented letters are not evidence. Green glyphs are
   left out without `--include-green`.
2. `build-accented-letters` adds each accented letter of a set that is not
   in the sources, as a purple composite at the offset
   `anchor of the base - anchor of the mark`, in every master, and adds it to
   `contents.plist` and `public.glyphOrder`. The sets are in
   `fontgarden/accented_letters.toml`. The default, `google-fonts-latin-core`,
   has the 145 accented letters of the Google Fonts Latin Core glyph set.
   `--replace-drafts` also sets the components of the purple accented
   letters again. The command lists the letters that it does not build:
   two marks, the caron of d, t, l and L, and the comma accent of g.
3. `render-accent-proofs` draws each accented letter of the project beside
   the same character in each family of the [reference fonts](#reference-fonts),
   at the weight of the master, and writes `review.json`. A letter gets a
   finding when its mark is outside the range of the reference fonts, not
   where the other accented letters of the project predict, or not where
   the anchors of its parts are. The sheets show every letter, the letters
   with findings first.

Both writing commands print their list and change nothing without `--write`.

The review is the work of an agent that can read images, or of the designer.
The task contract `accented-letters.md` and the skill `accent-review` of the
[project template](https://github.com/fontgarden/font-project-template) give
the method and the rules of a correct accented letter. The reviewer gives
each letter a verdict: `correct`, `fault` or `designer`. A finding is a
reason to look. It is not a fault, because the reference fonts do not
dictate the design.

A trial on Virtua Grotesk on 2026-11-15 removed all 145 accented letters
from a copy of both masters and built them again. With the anchors of the
designer in place, 269 of 280 composites (96%) were within 8 units of the
position of the designer. The other 11 are letters that the designer placed
away from the anchors, mostly ogoneks. With the `top` and `bottom` anchors
also removed, 60% were within 8 units and 80% within 20 units: the vertical
position was correct for all but one letter, and the horizontal position of
acute, grave, cedilla and ogonek needs the anchors of a designer or the
review.

## Reference fonts

One shared collection of OFL fonts serves every comparison and measurement:
the accent placement evaluation, proofs and checks. It is not a source of
outlines. Set `FONTGARDEN_REFERENCE_FONTS` to its directory, then run
`fgtools fetch-reference-fonts`. The command downloads the families of
`fontgarden/reference_fonts.toml` from https://github.com/google/fonts. That
file is the trusted list: each family has the reason that it is a reference,
and the designer decides which families it holds. Each family goes into `<directory>/<family>/` with its
`OFL.txt`. A family with variable fonts gets those. Another family gets its
Regular, Italic, Bold and Bold Italic. A family that is present is not
downloaded again, and `--family NAME` adds a family of `google/fonts/ofl`.

### Reference fonts of a project

Each project names its own reference families in `CONTEXT.md`:

```toml
[reference_fonts.families]
heebo = "A Hebrew extension of Roboto: a plain sans for text."
```

A key is a directory name of https://github.com/google/fonts under `ofl/`,
so the upstream of a family is
`https://github.com/google/fonts/tree/main/ofl/<name>`. The value is the
reason that the family is a reference. `fgtools fetch-reference-fonts
--project` (`make reference-fonts`) copies the upright fonts and the
`OFL.txt` of each family into `reference-fonts/<name>/` of the project. Git
ignores that folder. `proof-web` and Runebender read it. A family comes from
the first place that has it: the shared collection, a local clone of
google/fonts that `FONTGARDEN_GOOGLE_FONTS` names, or a download from GitHub.
The command lists the folders that `CONTEXT.md` does not name, and does not
remove them.

## Web proof

`fgtools proof-web --current` serves the current build beside the fonts in
`reference-fonts/`, at one em size and weight, on http://127.0.0.1:60272/.
The current build is the TTF with an `fvar` table in `<fonts>/variable/`, or
else the first TTF in the fonts directory. The page title is `familyName`
of `config.yaml`. The server reads `reference-fonts/` again when its files
change. It does not read the UFO sources, so build again after an edit.
`--check` prepares and checks the files and does not start the server.
Generated files go to `output/proof-web/`.

The modes are Compare, Toggle (Before and Candidate in place, key B),
Waterfall and Text. The samples are live browser text. The proof checks the
SHA-256 hash of each font before it shows it. A reference font without a
glyph shows the missing code points, not a fallback font. Browser rendering
is not release QA.

For a Before and Candidate comparison, write a comparison file with the
paths and hashes of fixed font files, run `proof-web prepare`, then
`proof-web --snapshot DIR`. The command remembers the snapshot, and
`proof-web` without a mode serves it again. If a Before or Candidate font is
missing, stop. Do not use the current build in its place. The manifest
format is in the docstring of `fontgarden/proof_web/prepare.py`.

### Samples

The package has default samples for Latin, Hebrew and Arabic in
`fontgarden/proof_web/samples.toml`. The proof uses a sample only when the
font has at least half of the basic letters of each script in its `scripts`.
`sources/proof-samples.toml` adds samples. A sample with the key of a
default sample replaces it. `defaults = false` removes all default samples.

```toml
defaults = true                 # false: use only the samples of this file

# A short sample for Compare, Toggle and Waterfall.
[sample.figures]
label = "Figures"
scripts = ["Latin"]             # optional: Latin, Hebrew or Arabic
text = "0123456789"
lang = "en"                     # optional: else the language of the first script

# A text sample for the Text mode.
[text.hebrew-news]
label = "Hebrew news"
scripts = ["Hebrew"]
overview = false                # true: each paragraph is a labeled section,
                                # and the sample is also in the other modes

[[text.hebrew-news.paragraphs]]
text = "..."                    # or `runs`, for mixed directions:
# runs = [{ text = "..." }, { text = "Latin", lang = "en", dir = "ltr" }]
# A paragraph can have `label`, `lang`, `dir` and `scripts`.
```

The proof also adds the sample "Encoded repertoire": every printable
character in the cmap of the font, by script.

## Guide

The guide of the Font.Garden system is at https://font.garden/docs. Its
source is https://github.com/fontgarden/fontgarden.github.io
(`src/content/docs/`). When you change a command, a `make` target, a mark
color, the layout or a workflow in this package, update the chapter of the guide in the
same session. The README of that repository lists the chapter for each kind
of change, and its `scripts/check_guide.py` finds the differences.

## Tests

```sh
python -m unittest discover -s tests
```

The tests build a small project with two masters in a temporary directory.
The proof-web tests also make small fonts with FontBuilder. The test of the
JavaScript face selection needs Node.js and is skipped without it.
To run the project tests on a real project too, set `FONTGARDEN_TEST_PROJECT`
to its root.

## License

Apache License 2.0. See [LICENSE](LICENSE).
