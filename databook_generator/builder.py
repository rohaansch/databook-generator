"""
DatabookBuilder — programmatic API for databook-generator.

All rendering utilities live here as module-level functions so they can be
imported independently.  The DatabookBuilder class wraps them into a
clean, chainable interface.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("PyYAML is required: pip install pyyaml")

try:
    from jinja2 import BaseLoader, Environment, TemplateSyntaxError, Undefined
except ImportError:
    raise ImportError("Jinja2 is required: pip install jinja2")

from databook_generator._version import __version__


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RENDERED_DIR = "_databook_rendered"
_RENDERED_IMAGES_DIR = "_databook_rendered/images"
_MASTER_ADOC = "_databook_master.adoc"
_THEME_FILE = "_databook_theme.yml"
_JINJA_PATTERN = re.compile(r"\{\{|\{%")


# ---------------------------------------------------------------------------
# Internal chapter representation
# ---------------------------------------------------------------------------

@dataclass
class _ChapterEntry:
    """One chapter in the book — either from chapters_dir or added dynamically."""
    name: str                                       # logical name; used for after/before lookup
    source: Path                                    # absolute path to the .adoc or .md file
    fmt: str                                        # 'adoc' or 'md'
    variables: dict = field(default_factory=dict)   # chapter-local vars (merged over global)
    images: list[Path] = field(default_factory=list)  # extra images to copy for this chapter


# ---------------------------------------------------------------------------
# Jinja2 helpers
# ---------------------------------------------------------------------------

class _SilentUndefined(Undefined):
    """Render undefined variables as empty strings instead of raising errors."""
    def __str__(self) -> str:
        return ""
    def __iter__(self):
        return iter([])
    def __bool__(self) -> bool:
        return False


def render_template(content: str, source_label: str, variables: dict) -> str:
    """Render arbitrary text as a Jinja2 template, returning the raw string on error."""
    try:
        template = Environment(
            loader=BaseLoader(),
            keep_trailing_newline=True,
            undefined=_SilentUndefined,
        ).from_string(content)
        return template.render(**variables)
    except TemplateSyntaxError as exc:
        print(f"WARNING: Jinja2 syntax error in {source_label}: {exc}", file=sys.stderr)
        return content
    except Exception as exc:
        print(f"WARNING: Jinja2 rendering failed for {source_label}: {exc}", file=sys.stderr)
        return content


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config_file(config_file: str | Path) -> dict:
    """Load and parse a JSON config file.  Raises on missing file or bad JSON."""
    path = Path(config_file)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse config file: {exc}") from exc


def validate_config(config: dict, require_chapters: bool = True) -> None:
    """Validate the config dict.  When require_chapters=False an empty list is allowed."""
    if not isinstance(config, dict):
        raise TypeError("Config must be a dict.")
    if "chapters" in config:
        if not isinstance(config["chapters"], list):
            raise ValueError("'chapters' must be a list.")
        if require_chapters and len(config["chapters"]) == 0:
            raise ValueError("'chapters' must be a non-empty list.")


# ---------------------------------------------------------------------------
# Chapter discovery
# ---------------------------------------------------------------------------

def find_chapter_file(chapters_dir: Path, name: str) -> tuple[Path, str] | None:
    """Return (path, 'adoc'|'md') for the first match, or None."""
    for ext in ("adoc", "md"):
        candidate = chapters_dir / f"{name}.{ext}"
        if candidate.exists():
            return candidate, ext
    return None


def detect_chapter_format(chapters_dir: Path, chapter_names: list[str]) -> str:
    """
    Return 'adoc' or 'md'.  Raises if no files found or formats are mixed.
    Only applies to chapters listed in the config (chapters_dir-based chapters).
    """
    formats: set[str] = set()
    for name in chapter_names:
        result = find_chapter_file(chapters_dir, name)
        if result:
            _, fmt = result
            formats.add(fmt)

    if not formats:
        raise FileNotFoundError(
            f"No chapter files found in {chapters_dir}. "
            "Ensure chapter files have a .adoc or .md extension."
        )
    if len(formats) > 1:
        raise ValueError(
            "Mix of .adoc and .md chapter files detected in chapters directory. "
            "All config-listed chapters must use the same format."
        )
    return formats.pop()


# ---------------------------------------------------------------------------
# Markdown → AsciiDoc conversion
# ---------------------------------------------------------------------------

def _require_pypandoc():
    try:
        import pypandoc
        return pypandoc
    except ImportError:
        raise ImportError(
            "'pypandoc' is required for Markdown chapters.\n"
            "  pip install pypandoc\n"
            "  Also install pandoc on your system:\n"
            "    macOS:   brew install pandoc\n"
            "    Linux:   sudo apt install pandoc\n"
            "    Windows: winget install --id JohnMacFarlane.Pandoc"
        )


def convert_md_to_adoc(md_content: str, source_label: str) -> str:
    """
    Convert Markdown to AsciiDoc via pypandoc.

    Shifts heading levels so Markdown ``##`` (pandoc output ``===``) becomes
    AsciiDoc ``==`` (level 1 in a book doctype).
    """
    pypandoc = _require_pypandoc()
    try:
        adoc = pypandoc.convert_text(
            md_content,
            to="asciidoc",
            format="markdown",
            extra_args=["--wrap=none"],
        )
    except Exception as exc:
        raise RuntimeError(f"pandoc conversion failed for {source_label}: {exc}") from exc

    lines = adoc.splitlines(keepends=True)
    has_level1 = any(re.match(r"^== [^=]", line) for line in lines)
    if not has_level1:
        shifted = []
        for line in lines:
            if re.match(r"^(={2,})\s", line):
                line = line[1:]
            shifted.append(line)
        adoc = "".join(shifted)

    return adoc


# ---------------------------------------------------------------------------
# Logo detection
# ---------------------------------------------------------------------------

def _find_file(images_dir: Path, stem: str) -> Path | None:
    for ext in ("svg", "png"):
        candidate = images_dir / f"{stem}.{ext}"
        if candidate.exists():
            return candidate
    return None


def find_logos(images_dir: Path) -> tuple[Path | None, Path | None]:
    """
    Return ``(main_logo, header_logo)``.

    Priority:
      ``main_logo``   → ``main_logo.svg/png``   → ``logo.svg/png``
      ``header_logo`` → ``header_logo.svg/png`` → ``logo.svg/png``
    """
    generic = _find_file(images_dir, "logo")
    main_logo = _find_file(images_dir, "main_logo") or generic
    header_logo = _find_file(images_dir, "header_logo") or generic
    return main_logo, header_logo


# ---------------------------------------------------------------------------
# Image preparation
# ---------------------------------------------------------------------------

def prepare_rendered_images(
    images_dir: Path,
    rendered_images_dir: Path,
    variables: dict,
    extra_images: list[Path] | None = None,
) -> None:
    """
    Copy every file from ``images_dir`` to ``rendered_images_dir``.
    SVGs containing Jinja2 directives are rendered first.
    ``extra_images`` (from dynamic chapters) are also copied.
    """
    rendered_images_dir.mkdir(parents=True, exist_ok=True)

    def _process(src: Path) -> None:
        dst = rendered_images_dir / src.name
        if src.suffix.lower() == ".svg":
            content = src.read_text(encoding="utf-8")
            if _JINJA_PATTERN.search(content):
                dst.write_text(
                    render_template(content, str(src), variables),
                    encoding="utf-8",
                )
            else:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)

    if images_dir.exists():
        for src in images_dir.iterdir():
            if src.is_file():
                _process(src)

    for src in (extra_images or []):
        if src.is_file():
            _process(src)
        else:
            print(f"WARNING: Extra image not found, skipping: {src}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Theme generation
# ---------------------------------------------------------------------------

def build_theme(main_logo: Path | None, header_logo: Path | None) -> dict:
    """
    Build an asciidoctor-pdf YAML theme dict.

    ``main_logo``   — centred on the title page at 45 % page width.
    ``header_logo`` — top-right of every page header at 22 % page width.
    Absolute paths are used so the theme works regardless of CWD.
    """
    main_ref = (
        f"image:{main_logo.resolve()}[pdfwidth=45%,align=center]"
        if main_logo else None
    )
    header_ref = (
        f"image:{header_logo.resolve()}[pdfwidth=22%]"
        if header_logo else None
    )

    theme: dict = {
        "extends": "default",
        "page": {"margin": ["0.75in", "0.67in", "0.75in", "0.67in"]},
        "base": {"font-size": 10.5, "line-height": 1.4},
        "heading": {"font-style": "bold"},
        "code": {"font-size": 9},
    }

    if main_ref:
        theme["title-page"] = {
            "logo": {"image": main_ref, "top": "8%", "align": "center"}
        }
    if header_ref:
        theme["header"] = {
            "height": "0.7in",
            "line-height": 1,
            "border-width": 0,
            "recto": {"right": {"content": header_ref}},
            "verso": {"right": {"content": header_ref}},
        }

    theme["footer"] = {
        "border-width": 0.25,
        "border-color": "AAAAAA",
        "recto": {
            "left": {"content": "{doctitle}"},
            "right": {"content": "Page {page-number} of {page-count}"},
        },
        "verso": {
            "left": {"content": "Page {page-number} of {page-count}"},
            "right": {"content": "{doctitle}"},
        },
    }
    return theme


# ---------------------------------------------------------------------------
# Master .adoc assembly
# ---------------------------------------------------------------------------

def assemble_master_adoc(
    title: str,
    rendered_chapters: list[tuple[str, Path]],
    rendered_images_dir: Path,
    author: str = "",
) -> str:
    """Return the content of the top-level master AsciiDoc document."""
    lines: list[str] = [f"= {title}"]
    if author:
        lines.append(f":author: {author}")
    lines += [
        ":chapter-label:",
        ":sectnums:",
        ":reproducible:",
        ":listing-caption: Listing",
        ":source-highlighter: rouge",
        ":toc:",
        ":toclevels: 3",
        ":toc-title: Table of Contents",
        ":pdf-page-size: A4",
        ":doctype: book",
        f":imagesdir: {rendered_images_dir.resolve()}",
        "",
    ]
    for name, adoc_path in rendered_chapters:
        if adoc_path.exists():
            lines.append(f"include::{adoc_path.resolve()}[]")
            lines.append("")
        else:
            print(f"WARNING: Rendered chapter not found, skipping: {name}", file=sys.stderr)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# asciidoctor-pdf discovery
# ---------------------------------------------------------------------------

def find_asciidoctor_pdf() -> str:
    """Search PATH and common gem install locations for the asciidoctor-pdf binary."""
    found = shutil.which("asciidoctor-pdf")
    if found:
        return found

    candidates: list[str] = []

    for gem_bin in ["/opt/homebrew/bin/gem", "/usr/local/bin/gem"]:
        if Path(gem_bin).exists():
            try:
                result = subprocess.run(
                    [gem_bin, "env", "EXECUTABLE DIRECTORY"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    candidates.append(f"{result.stdout.strip()}/asciidoctor-pdf")
            except Exception:
                pass
            break

    try:
        result = subprocess.run(
            ["brew", "--prefix", "ruby"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            brew_ruby = result.stdout.strip()
            for ver in ("4.0.0", "3.3.0", "3.2.0", "3.1.0"):
                candidates.append(
                    str((Path(brew_ruby) / f"../../../lib/ruby/gems/{ver}/bin/asciidoctor-pdf").resolve())
                )
    except Exception:
        pass

    home = Path.home()
    for ver in ("4.0.0", "3.3.0", "3.2.0", "3.1.0", "3.0.0", "2.7.0"):
        candidates.append(str(home / f".gem/ruby/{ver}/bin/asciidoctor-pdf"))

    if (home / ".rbenv/versions").exists():
        for p in (home / ".rbenv/versions").glob("*/bin/asciidoctor-pdf"):
            candidates.append(str(p))

    for c in candidates:
        if Path(c).exists():
            return c

    return ""


def check_asciidoctor_pdf() -> str:
    """Return the asciidoctor-pdf binary path, or raise RuntimeError."""
    binary = find_asciidoctor_pdf()
    if not binary:
        raise RuntimeError(
            "'asciidoctor-pdf' is not installed or not in PATH.\n\n"
            "Install instructions:\n"
            "  macOS:    gem install asciidoctor-pdf\n"
            "            (Homebrew Ruby: $(brew --prefix ruby)/bin/gem install asciidoctor-pdf)\n"
            "  Linux:    gem install asciidoctor-pdf\n"
            "  Windows:  gem install asciidoctor-pdf  (requires RubyInstaller)\n\n"
            "If installed but not found:\n"
            "  export PATH=\"$(gem environment gemdir)/bin:$PATH\""
        )
    return binary


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_pdf(master_adoc: Path, theme_file: Path, output_pdf: Path, binary: str) -> int:
    cmd = [
        binary,
        "-a", f"pdf-theme={theme_file.resolve()}",
        "-o", str(output_pdf),
        str(master_adoc),
    ]
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup(paths: list[Path]) -> None:
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file():
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# DatabookBuilder
# ---------------------------------------------------------------------------

class DatabookBuilder:
    """
    Programmatic API for building PDF databooks.

    Accepts a config as either a Python ``dict`` or a path to a JSON file.
    Chapters listed in the config are loaded from ``chapters_dir``.  Additional
    chapters can be injected at any position via :meth:`add_chapter`.

    **Minimal example — config dict only:**

    .. code-block:: python

        from databook_generator import DatabookBuilder

        builder = DatabookBuilder(
            config={
                "title": "My Report",
                "version": "1.0",
                "product": "XR-9000",
                "chapters": ["overview", "measurements"],
            },
            chapters_dir="chapters",
            images_dir="images",
        )
        builder.build(output="report.pdf")

    **Dynamic chapter insertion:**

    .. code-block:: python

        builder.add_chapter(
            template_path="templates",
            template_file="cell_library.adoc",
            variables={
                "cells": [
                    {
                        "name": "NAND2_X1",
                        "description": "2-input NAND, drive strength 1",
                        "inputs": ["A", "B"],
                        "output": "ZN",
                        "area_um2": 0.42,
                        "schematic": "nand2_schematic.svg",
                    },
                    {
                        "name": "INV_X1",
                        "description": "Inverter, drive strength 1",
                        "inputs": ["A"],
                        "output": "ZN",
                        "area_um2": 0.21,
                        "schematic": "inv_schematic.svg",
                    },
                ]
            },
            images=[
                "templates/images/nand2_schematic.svg",
                "templates/images/inv_schematic.svg",
            ],
            after="overview",   # inserted between "overview" and "measurements"
        )
        builder.build(output="report_with_cells.pdf")
    """

    def __init__(
        self,
        config: dict | str | Path,
        chapters_dir: str | Path | None = None,
        images_dir: str | Path | None = None,
        output: str | Path | None = None,
    ) -> None:
        """
        Args:
            config:       Config as a Python ``dict`` *or* a path to a JSON file.
                          Required keys: ``title``.  Optional but common: ``chapters``
                          (list of chapter names), ``author``, and any Jinja2 variables.
            chapters_dir: Directory containing the ``.adoc`` / ``.md`` files listed in
                          ``config["chapters"]``.  Defaults to ``chapters/`` in CWD.
                          Not required when all chapters are added via :meth:`add_chapter`.
            images_dir:   Directory containing shared images (logo, diagrams).
                          Defaults to ``images/`` in CWD.
            output:       Default output PDF path.  Can be overridden in :meth:`build`.
        """
        self._cwd = Path.cwd()

        if isinstance(config, dict):
            self._config: dict = config
        else:
            self._config = load_config_file(config)

        # Allow empty/absent chapters list — all chapters may come via add_chapter()
        validate_config(self._config, require_chapters=False)

        self._chapters_dir = (
            Path(chapters_dir).resolve() if chapters_dir
            else self._cwd / "chapters"
        )
        self._images_dir = (
            Path(images_dir).resolve() if images_dir
            else self._cwd / "images"
        )
        self._default_output: Path | None = (
            Path(output).resolve() if output else None
        )

        # Global Jinja2 variables: everything in config except "chapters"
        self._global_vars: dict = {
            k: v for k, v in self._config.items() if k != "chapters"
        }

        # Populate initial chapter list from config["chapters"]
        self._chapters: list[_ChapterEntry] = []
        for name in self._config.get("chapters", []):
            result = find_chapter_file(self._chapters_dir, name)
            if result is None:
                print(
                    f"WARNING: Chapter '{name}' not found in {self._chapters_dir}",
                    file=sys.stderr,
                )
                continue
            src, fmt = result
            self._chapters.append(_ChapterEntry(name=name, source=src, fmt=fmt))

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def chapter_names(self) -> list[str]:
        """Current ordered list of chapter names (read-only)."""
        return [ch.name for ch in self._chapters]

    @property
    def global_vars(self) -> dict:
        """Copy of the global Jinja2 variables derived from the config."""
        return dict(self._global_vars)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add_chapter(
        self,
        template_path: str | Path,
        template_file: str,
        variables: dict | None = None,
        images: list[str | Path] | None = None,
        after: str | None = None,
        before: str | None = None,
        position: int | None = None,
        name: str | None = None,
    ) -> "DatabookBuilder":
        """
        Add a dynamically generated chapter from a Jinja2 template file.

        The chapter is rendered by merging the **global config variables** with
        the chapter-specific ``variables`` dict — chapter keys take precedence,
        so a chapter can override any global variable for its own scope.

        Args:
            template_path:  Directory that contains the template file.
            template_file:  Filename of the ``.adoc`` or ``.md`` template
                            (e.g. ``"cell_library.adoc"``).
            variables:      Chapter-specific Jinja2 variables.  Merged *over*
                            the global config variables.
            images:         Image files this chapter needs.  Each file is copied
                            into the shared rendered-images directory so the
                            template can reference images by filename only
                            (e.g. ``image::nand2_schematic.svg[]``).
                            Paths may be absolute or relative to CWD.
            after:          Insert this chapter immediately *after* the named
                            chapter.  Takes priority over ``before`` and
                            ``position``.
            before:         Insert this chapter immediately *before* the named
                            chapter.  Takes priority over ``position``.
            position:       Zero-based index to insert at.  Used only when
                            neither ``after`` nor ``before`` is given.
            name:           Logical name for this chapter — used for subsequent
                            ``after``/``before`` lookups.  Must be unique within
                            the builder.  Defaults to the template file stem.

        Returns:
            ``self`` so calls can be chained.

        Raises:
            FileNotFoundError: Template file does not exist.
            ValueError:        Template is not ``.adoc`` or ``.md``, or a chapter
                               with the same ``name`` already exists, or the
                               ``after``/``before`` chapter name is not found.
        """
        src = Path(template_path).resolve() / template_file
        if not src.exists():
            raise FileNotFoundError(f"Template not found: {src}")

        fmt = src.suffix.lstrip(".").lower()
        if fmt not in ("adoc", "md"):
            raise ValueError(
                f"Template must be .adoc or .md, got: '{src.suffix}'"
            )

        chapter_name = name or src.stem
        if any(ch.name == chapter_name for ch in self._chapters):
            raise ValueError(
                f"A chapter named '{chapter_name}' already exists. "
                "Assign a unique name with the `name` parameter."
            )

        entry = _ChapterEntry(
            name=chapter_name,
            source=src,
            fmt=fmt,
            variables=dict(variables or {}),
            images=[Path(p).resolve() for p in (images or [])],
        )

        if after is not None:
            self._chapters.insert(self._index_of(after) + 1, entry)
        elif before is not None:
            self._chapters.insert(self._index_of(before), entry)
        elif position is not None:
            self._chapters.insert(position, entry)
        else:
            self._chapters.append(entry)

        return self   # allow chaining

    def build(
        self,
        output: str | Path | None = None,
        keep_intermediates: bool = False,
    ) -> Path:
        """
        Render all chapters, apply the theme, and generate the PDF.

        Args:
            output:              Output PDF path.  Overrides the path passed to
                                 ``__init__``, which in turn falls back to
                                 ``<title>.pdf`` in CWD.
            keep_intermediates:  Retain intermediate rendered ``.adoc`` files
                                 and the theme YAML after the PDF is written.
                                 Useful for debugging template output.

        Returns:
            :class:`pathlib.Path` to the generated PDF.

        Raises:
            ValueError:   No chapters to render.
            RuntimeError: ``asciidoctor-pdf`` not found, or exits non-zero.
        """
        if not self._chapters:
            raise ValueError(
                "No chapters to render. "
                "Add chapters via config['chapters'] or add_chapter()."
            )

        title = self._config.get("title", "Databook")
        author = self._config.get("author", "")

        if output:
            output_pdf = Path(output).resolve()
        elif self._default_output:
            output_pdf = self._default_output
        else:
            safe_title = re.sub(r"[^\w\-]", "_", title)
            output_pdf = self._cwd / f"{safe_title}.pdf"

        asciidoctor_bin = check_asciidoctor_pdf()

        print(f"databook-generator v{__version__}")
        print(f"Chapters: {len(self._chapters)}  →  {', '.join(self.chapter_names)}")
        print(f"Images:   {self._images_dir}")
        print(f"Output:   {output_pdf}")
        print()

        rendered_images_dir = self._cwd / _RENDERED_IMAGES_DIR

        # Collect all per-chapter extra images up front
        all_extra_images: list[Path] = [
            img for ch in self._chapters for img in ch.images
        ]

        # Logo detection (points at rendered copies, which may not exist yet)
        main_logo_src, header_logo_src = find_logos(self._images_dir)
        rendered_main_logo = (rendered_images_dir / main_logo_src.name) if main_logo_src else None
        rendered_header_logo = (rendered_images_dir / header_logo_src.name) if header_logo_src else None
        self._log_logos(main_logo_src, header_logo_src)

        # Prepare images (copy + Jinja2 render SVGs)
        prepare_rendered_images(
            self._images_dir,
            rendered_images_dir,
            self._global_vars,
            extra_images=all_extra_images,
        )
        print(f"Images prepared: {rendered_images_dir}")

        # Build and write theme
        theme_dict = build_theme(rendered_main_logo, rendered_header_logo)
        theme_file = self._cwd / _THEME_FILE
        with open(theme_file, "w", encoding="utf-8") as fh:
            yaml.dump(theme_dict, fh, default_flow_style=False, allow_unicode=True)
        print(f"Theme written: {theme_file.name}")

        # Render chapters
        rendered_chapters_dir = self._cwd / _RENDERED_DIR
        rendered_chapters_dir.mkdir(exist_ok=True)

        rendered: list[tuple[str, Path]] = []
        for ch in self._chapters:
            adoc_path = self._render_chapter(ch, rendered_chapters_dir)
            if adoc_path:
                rendered.append((ch.name, adoc_path))

        print(f"Rendered {len(rendered)}/{len(self._chapters)} chapters.")

        if not rendered:
            _cleanup([rendered_chapters_dir, rendered_images_dir, theme_file])
            raise RuntimeError("No chapters were rendered successfully.")

        # Assemble master .adoc
        master_adoc_path = self._cwd / _MASTER_ADOC
        master_adoc_path.write_text(
            assemble_master_adoc(
                title=title,
                rendered_chapters=rendered,
                rendered_images_dir=rendered_images_dir,
                author=author,
            ),
            encoding="utf-8",
        )
        print(f"Master .adoc assembled: {master_adoc_path.name}")

        # Generate PDF
        print()
        ret = generate_pdf(master_adoc_path, theme_file, output_pdf, asciidoctor_bin)

        intermediates = [rendered_chapters_dir, rendered_images_dir, master_adoc_path, theme_file]
        if keep_intermediates:
            print("\nIntermediate files kept:")
            for p in intermediates:
                print(f"  {p}")
        else:
            _cleanup(intermediates)

        if ret != 0:
            raise RuntimeError(f"asciidoctor-pdf exited with code {ret}.")

        print(f"\nPDF generated successfully: {output_pdf}")
        return output_pdf

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _index_of(self, chapter_name: str) -> int:
        for i, ch in enumerate(self._chapters):
            if ch.name == chapter_name:
                return i
        raise ValueError(
            f"Chapter '{chapter_name}' not found. "
            f"Available: {self.chapter_names}"
        )

    def _render_chapter(self, ch: _ChapterEntry, rendered_dir: Path) -> Path | None:
        """Render one chapter entry to an .adoc file.  Returns the path or None on failure."""
        merged = {**self._global_vars, **ch.variables}   # chapter vars override globals
        try:
            content = ch.source.read_text(encoding="utf-8")
            rendered = render_template(content, str(ch.source), merged)
            if ch.fmt == "md":
                rendered = convert_md_to_adoc(rendered, str(ch.source))
            out = rendered_dir / f"{ch.name}.adoc"
            out.write_text(rendered, encoding="utf-8")
            return out
        except Exception as exc:
            print(f"WARNING: Failed to render chapter '{ch.name}': {exc}", file=sys.stderr)
            return None

    @staticmethod
    def _log_logos(main: Path | None, header: Path | None) -> None:
        if main and header:
            if main == header:
                print(f"Logo detected: {main.name} (title page + header)")
            else:
                print(f"Main logo:   {main.name}")
                print(f"Header logo: {header.name}")
        else:
            print(
                "No logo detected. Place logo.svg/png, main_logo.svg/png, or "
                "header_logo.svg/png in the images directory."
            )
