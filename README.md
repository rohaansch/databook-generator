# databook-generator

<p align="center">
  <img src="assets/logo.svg" alt="Company Logo" width="480"/>
</p>

[![PyPI version](https://img.shields.io/pypi/v/databook-generator)](https://pypi.org/project/databook-generator/)
[![Python versions](https://img.shields.io/pypi/pyversions/databook-generator)](https://pypi.org/project/databook-generator/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Generate polished PDF databooks from **AsciiDoc** or **Markdown** chapter files, with full **Jinja2 templating** throughout — including inside SVG diagrams.

Define your parameters once in a `config.json` file. Every parameter automatically becomes a variable you can reference inside your chapter content and your SVG images.

---

## Features

- **AsciiDoc** (`.adoc`) chapters rendered via `asciidoctor-pdf`
- **Markdown** (`.md`) chapters converted to AsciiDoc via `pandoc`, then rendered to PDF with the same pipeline
- **Jinja2 templating** in `.adoc`, `.md`, and `.svg` files — any key in `config.json` becomes a template variable
- **Logo support** — drop `logo.svg` or `logo.png` in your `images/` folder; it appears on the title page and in the top-right corner of every page
- **Per-page footer** with document title and page numbers
- Auto-discovery of `asciidoctor-pdf` binary across Homebrew, gem user-install, rbenv, and RVM
- Clean intermediate file handling — no leftover artefacts unless you ask for them

---

## Requirements

### Python

Python 3.8 or newer.

### asciidoctor-pdf (required for all PDFs)

`asciidoctor-pdf` is a Ruby gem and must be installed separately.

#### macOS

```bash
# If you have the system Ruby (not recommended — no write permission):
gem install asciidoctor-pdf --user-install

# Recommended: install Ruby via Homebrew first
brew install ruby
$(brew --prefix ruby)/bin/gem install asciidoctor-pdf

# Add Homebrew gem bin to your PATH permanently (add to ~/.zshrc or ~/.bashrc):
export PATH="$(brew --prefix ruby)/bin:$PATH"
export PATH="$($(brew --prefix ruby)/bin/gem environment gemdir)/bin:$PATH"
```

#### Linux (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install ruby-full build-essential
gem install asciidoctor-pdf
```

#### Linux (Fedora / RHEL / CentOS)

```bash
sudo dnf install ruby ruby-devel
gem install asciidoctor-pdf
```

#### Windows

1. Download and install Ruby from [rubyinstaller.org](https://rubyinstaller.org/) (include the MSYS2 toolchain when prompted).
2. Open a new Command Prompt or PowerShell:

```powershell
gem install asciidoctor-pdf
```

#### Verify installation

```bash
asciidoctor-pdf --version
# If not found, locate the gem bin directory:
gem environment gemdir
# Then add <gemdir>/bin to your PATH
```

---

### pandoc (required only for Markdown chapters)

`pandoc` is only needed when your chapters are `.md` files.

#### macOS

```bash
brew install pandoc
```

#### Linux (Debian / Ubuntu)

```bash
sudo apt install pandoc
```

#### Linux (Fedora / RHEL)

```bash
sudo dnf install pandoc
```

#### Windows

```powershell
winget install --id JohnMacFarlane.Pandoc
# Or download the installer from https://pandoc.org/installing.html
```

#### Verify installation

```bash
pandoc --version
```

---

## Installation

### From PyPI

```bash
pip install databook-generator
```

### With Markdown support

```bash
pip install "databook-generator[markdown]"
```

### From source

```bash
git clone https://github.com/rohaansch/databook-generator.git
cd databook-generator
pip install -e .                   # AsciiDoc chapters only
pip install -e ".[markdown]"       # Include Markdown support
```

---

## Quick Start

### 1. Create your working directory

```
my-databook/
├── config.json
├── chapters/
│   ├── introduction.adoc   (or introduction.md)
│   └── chapter2.adoc       (or chapter2.md)
└── images/
    ├── logo.svg            (optional — auto-detected)
    └── my_diagram.svg
```

### 2. Write your config

```json
{
    "title": "My Databook",
    "version": "1.0",
    "author": "Your Name",
    "date": "April 2026",
    "product_name": "Widget Pro",
    "chapters": [
        "introduction",
        "chapter2"
    ]
}
```

### 3. Run

```bash
cd my-databook/
databook-generator -config config.json
```

The PDF is written to `my-databook/My_Databook.pdf`.

---

## CLI Reference

```
databook-generator -config CONFIG [options]

Required:
  -config FILE        Path to the JSON config file

Optional:
  -images DIR         Images directory (default: ./images)
  -chapters DIR       Chapters directory (default: ./chapters)
  -output FILE        Output PDF path (default: <title>.pdf in CWD)
  --keep-intermediates  Keep rendered .adoc and theme files for debugging
  --version           Show version and exit
  -h, --help          Show help
```

---

## Config File Reference

`config.json` drives both the document structure and Jinja2 template variables.

| Key | Required | Description |
|---|---|---|
| `title` | Yes | Document title — used on the title page, footer, and output filename |
| `chapters` | Yes | Ordered list of chapter names (without extension) |
| `author` | No | Author name displayed on the title page |
| Any other key | No | Automatically available as a Jinja2 variable in chapters and SVGs |

### Example

```json
{
    "title": "Specification Document",
    "version": "2.1",
    "author": "Rohan Chadhury",
    "date": "April 2024",
    "support_email": "support@example.com",
    "feature_flags": {
        "include_legacy_notes": false,
        "include_new_section": true
    },
    "chapters": [
        "introduction",
        "measurements",
        "api_example"
    ]
}
```

---

## Jinja2 Templating

This is the core power feature of `databook-generator`. Every key you define in `config.json` is injected as a Jinja2 variable into your chapter files and SVG images at render time.

### How it works

When you run `databook-generator`, it:
1. Loads your `config.json`
2. Passes every key (except `"chapters"`) as a Jinja2 variable
3. Renders each chapter file as a Jinja2 template
4. Renders any SVG files that contain Jinja2 syntax
5. Assembles and generates the final PDF

### Variable substitution

Use `{{ variable_name }}` anywhere in your chapter or SVG:

```
# In config.json:
"author": "Rohan Chadhury",
"date": "April 2026",
"revision": "Rev1.0"

# In a chapter file (.adoc or .md):
This document covers the Measurements for revision {{ revision }} released on date {{ date }}.
```

Renders to:

```
This document covers the Measurements for revision Rev1.0 released on date April 2026
```

### Conditional content

Use `{% if %}` / `{% else %}` / `{% endif %}` to include or exclude sections:

```
# config.json:
"feature_flags": { "include_legacy_notes": false }

# chapter.adoc:
{% if feature_flags.include_legacy_notes %}
NOTE: This section contains legacy notes for pre-{{ revision }} users.
...
{% endif %}
```

If `include_legacy_notes` is `false`, that entire block is omitted from the PDF.

### Loops

Use `{% for %}` to generate repeated content from a list:

```
# config.json:
"layer_stack": ["M1", "M2", "M3", "M4", "M5"]

# chapter.adoc:
The following measurements are defined in {{ revision }}:

{% for timing in measurements %}
* {{ timing }}
{% endfor %}
```

### Nested values

Access nested config keys using dot notation:

```
# config.json:
"timing": { "setup_margin": "50ps", "hold_margin": "20ps" }

# chapter.md:
Setup margin: **{{ timing.setup_margin }}**
Hold margin: **{{ timing.hold_margin }}**
```

### SVG templating

SVG files in your `images/` directory are also Jinja2 templates.
Any SVG containing `{{` or `{%` is rendered before embedding in the PDF.

```xml
<!-- images/product_image.svg -->
<text x="300" y="50">{{ document_name }} — {{ serial_number }}</text>
<text x="300" y="70">Rev: {{ revision }}</text>
```

This is useful for diagram titles, labels, and revision stamps that should always
match the config — no need to manually update SVG text when values change.

### Undefined variables

If a template references a variable not present in `config.json`, it silently
renders as an empty string (no errors). This lets you write reusable chapter
templates that gracefully degrade for configs that don't define every variable.

---

## Chapter Formats

### AsciiDoc (`.adoc`)

AsciiDoc is a rich markup format with native support for tables, cross-references,
callouts, and admonitions. It is the recommended format for complex technical documents.

```asciidoc
== Introduction

This spec covers *{{ document_name }}* revision *{{ revision }}*.

[cols="1,2", options="header"]
|===
| Field | Value
| Document Title | {{ document_name }}
| Revision | {{ revision }}
|===

[NOTE]
====
All measurements are in nanometers.
====

<<<
```

The `<<<` at the end of a chapter inserts a page break.

### Markdown (`.md`)

Markdown chapters use standard GitHub-Flavoured Markdown (GFM).
Under the hood they are converted to AsciiDoc via `pandoc` before PDF generation,
so the same logo, theme, and footer apply.

```markdown
## Introduction

This report covers **{{ product_name }}** on the **{{ model_number }}** node.

| Field | Value |
|---|---|
| Product | {{ product_name }} |
| Node | {{ model_number }} |

{% if include_appendix %}
> See the appendix for raw measurement data.
{% endif %}
```

### Format rules

- All chapters in a run must use the **same format** — either all `.adoc` or all `.md`.
- Do not mix `.adoc` and `.md` in the same `chapters` list. The tool will exit with an error if mixed files are detected.
- The extension is **not** included in `config.json`; the tool discovers it automatically.

---

## Logo

Place one or more logo files in your `images/` directory. No configuration is needed — detection is automatic. SVG is recommended for crisp rendering at all sizes.

### Two-logo mode (recommended)

Use separate files optimised for each context:

| File | Where it appears | Recommended size |
|---|---|---|
| `main_logo.svg` / `main_logo.png` | Centred on the **title page** at 45% page width | Wide, high-resolution |
| `header_logo.svg` / `header_logo.png` | Top-right of **every page header** at 22% page width | Horizontal / compact |

### Single-logo mode (fallback)

If dedicated files are not found, `logo.svg` / `logo.png` is used for both roles automatically.

### Priority order

```
Title page  → main_logo.svg/png   → logo.svg/png
Header      → header_logo.svg/png → logo.svg/png
```

### SVG logo templating

Logo SVG files can contain Jinja2 directives just like chapter files. For example, to stamp a version number on the logo:

```xml
<!-- images/header_logo.svg -->
<text x="200" y="60">Rev {{ version }}</text>
```

---

## Directory Layout

The expected layout when running from a project directory:

```
my-databook/
├── config.json          Required
├── chapters/            Default chapter directory (override with -chapters)
│   ├── intro.adoc       or intro.md
│   └── section2.adoc    or section2.md
└── images/              Default images directory (override with -images)
    ├── logo.svg          Auto-detected logo
    └── diagram.svg       Referenced from chapters as image::diagram.svg[]
```

Override defaults:

```bash
databook-generator \
  -config /path/to/config.json \
  -chapters /path/to/my/chapters \
  -images /path/to/my/images \
  -output /path/to/output/report.pdf
```

---

## Syntax Highlighting

Code blocks in chapters use [Rouge](https://rouge.jneen.net/) for syntax highlighting.
Install it for coloured output:

```bash
gem install rouge
```

---

## Python API

`DatabookBuilder` lets you drive the entire build from Python code — no CLI, no `config.json` required.

### Basic usage

```python
from databook_generator import DatabookBuilder

builder = DatabookBuilder(
    config={
        "title": "Device Characterization Report",
        "version": "3.0",
        "product": "XR-9000",
        "process_node": "5nm FinFET",
        "chapters": ["overview", "measurements"],
    },
    chapters_dir="chapters",
    images_dir="images",
)
builder.build(output="report.pdf")
```

You can also pass a path to a JSON file instead of a dict:

```python
builder = DatabookBuilder(config="config.json", chapters_dir="chapters", images_dir="images")
```

### Injecting custom chapters

Use `add_chapter()` to insert a dynamically generated chapter at any position.
The chapter content is a Jinja2 template; you supply the variables at call time.

```python
builder.add_chapter(
    template_path="templates",          # directory containing the template
    template_file="cell_library.adoc",  # .adoc or .md template
    variables={                         # Jinja2 variables for this chapter only
        "cells": [
            {
                "name": "NAND2_X1",
                "description": "2-input NAND gate",
                "inputs": ["A", "B"],
                "output": "ZN",
                "area_um2": 0.42,
            },
            {
                "name": "INV_X1",
                "description": "Inverter",
                "inputs": ["A"],
                "output": "ZN",
                "area_um2": 0.21,
            },
        ]
    },
    images=[                            # images this chapter needs
        "templates/images/nand2_schematic.svg",
        "templates/images/inv_schematic.svg",
    ],
    after="overview",                   # insert after the 'overview' chapter
    name="cell_library",                # logical name for after/before lookups
)

print(builder.chapter_names)
# → ['overview', 'cell_library', 'measurements']

builder.build()
```

#### Positioning options

| Parameter | Behaviour |
|---|---|
| `after="chapter_name"` | Insert immediately after the named chapter |
| `before="chapter_name"` | Insert immediately before the named chapter |
| `position=N` | Insert at zero-based index N |
| *(none)* | Append to the end |

`add_chapter()` returns `self`, so calls can be chained.

#### Chapter-local variables

Variables passed to `add_chapter(variables=...)` are **merged over** the global config variables — chapter-level keys override global ones for that chapter's scope only. Global variables are still available in the template.

### Keeping intermediate files

Pass `keep_intermediates=True` to `build()` to retain the rendered `.adoc` files and theme YAML for debugging:

```python
builder.build(output="report.pdf", keep_intermediates=True)
```

---

## Examples

The `example/` directory contains three complete working examples:

### AsciiDoc example

```bash
cd example/adoc_example/
databook-generator -config config.json
```

Demonstrates:
- Jinja2 variable substitution and conditionals in `.adoc`
- SVG diagrams with Jinja2 labels rendered at build time
- Logo on every page

### Markdown example

```bash
cd example/markdown_example/
databook-generator -config config.json
```

Demonstrates:
- Jinja2 variable substitution and conditionals in `.md`
- GFM tables and code fences
- Chart SVGs referenced from Markdown

### Python API example

```bash
cd example/api_example/
python generate_report.py
```

Demonstrates the full Python API:
- `DatabookBuilder` instantiated with a config dict loaded from JSON
- A custom `Cell Library` chapter generated from a Jinja2 template and a list of cell dicts
- Cell schematics injected as chapter-local images
- Chapter inserted between `overview` and `measurements` using `after="overview"`

The example directory layout:

```
example/api_example/
├── config.json                      Standard config (overview + measurements)
├── chapters/                        Standard chapter files
│   ├── overview.adoc
│   └── measurements.adoc
├── images/                          Shared images (logo, charts)
├── templates/                       Custom chapter templates
│   ├── cell_library.adoc            Jinja2 template — loops over a list of cells
│   └── images/                      Cell-specific schematics
│       ├── nand2_schematic.svg
│       └── inv_schematic.svg
└── generate_report.py               Python script using DatabookBuilder
```

---

## Releasing to PyPI

### Setup (one time)

1. Create a [PyPI account](https://pypi.org/account/register/)
2. Enable Trusted Publishing in your PyPI project settings, pointing to this repository and the `publish.yml` workflow

### Release process

```bash
# Bump version in:
#   databook_generator/__init__.py  (VERSION)
#   pyproject.toml                  (version field)
#   CHANGELOG.md                    (add entry)

git add .
git commit -m "Release v1.1.0"
git tag v1.1.0
git push origin main --tags
```

The GitHub Actions workflow (`.github/workflows/publish.yml`) automatically builds
and publishes to PyPI when a `v*.*.*` tag is pushed.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes and add tests
4. Push and open a PR against `main`

---

## License

[MIT](LICENSE) — © 2024 Rohan Chadhury
