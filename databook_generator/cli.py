#!/usr/bin/env python3
"""
databook-generator — Generate PDF databooks from AsciiDoc or Markdown chapters
with Jinja2 templating.

Usage:
    databook-generator -config config.json
    databook-generator -config config.json -images path/to/images -chapters path/to/chapters
    databook-generator -config config.json -output my_databook.pdf

Every key in config.json (except "chapters") becomes a Jinja2 variable available
inside .adoc, .md, and .svg files.

Required external tools:
    asciidoctor-pdf   (gem install asciidoctor-pdf)
    pandoc            (https://pandoc.org/installing.html) — only for Markdown chapters

Author: Rohan Chadhury <rohaanshahid@gmail.com>
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from databook_generator import __version__

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required.  pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from jinja2 import Environment, BaseLoader, TemplateSyntaxError
except ImportError:
    print("ERROR: Jinja2 is required.  pip install jinja2", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RENDERED_DIR = "_databook_rendered"
_RENDERED_IMAGES_DIR = "_databook_rendered/images"
_MASTER_ADOC = "_databook_master.adoc"
_THEME_FILE = "_databook_theme.yml"
_JINJA_PATTERN = re.compile(r"\{\{|\{%")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="databook-generator",
        description=(
            "Generate a PDF databook from AsciiDoc or Markdown chapters "
            "with Jinja2 templating."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-config", required=True, metavar="FILE",
        help="Path to the JSON config file (required).",
    )
    parser.add_argument(
        "-images", metavar="DIR", default=None,
        help="Directory containing images (default: images/ in CWD).",
    )
    parser.add_argument(
        "-chapters", metavar="DIR", default=None,
        help="Directory containing chapter files (default: chapters/ in CWD).",
    )
    parser.add_argument(
        "-output", metavar="FILE", default=None,
        help="Output PDF path (default: <title>.pdf in CWD).",
    )
    parser.add_argument(
        "--keep-intermediates", action="store_true",
        help="Keep intermediate .adoc and theme files after PDF generation.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_file: str) -> dict:
    path = Path(config_file)
    if not path.exists():
        print(f"ERROR: Config file not found: {config_file}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Failed to parse config file: {exc}", file=sys.stderr)
            sys.exit(1)


def validate_config(config: dict) -> None:
    if "chapters" not in config:
        print(
            "ERROR: config.json must contain a 'chapters' key with a list of chapter names.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(config["chapters"], list) or len(config["chapters"]) == 0:
        print("ERROR: 'chapters' must be a non-empty list.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Chapter format detection
# ---------------------------------------------------------------------------

def find_chapter_file(chapters_dir: Path, name: str) -> tuple[Path, str] | None:
    """
    Return (path, fmt) where fmt is 'adoc' or 'md'.
    Prefers .adoc if both exist for the same name (should not happen in practice).
    """
    for ext in ("adoc", "md"):
        candidate = chapters_dir / f"{name}.{ext}"
        if candidate.exists():
            return candidate, ext
    return None


def detect_chapter_format(chapters_dir: Path, chapter_names: list[str]) -> str:
    """
    Return 'adoc' or 'md'.  Exits with an error if:
      - No chapter files are found at all.
      - Both .adoc and .md files exist across the chapter list (mix-and-match).
    """
    formats: set[str] = set()
    for name in chapter_names:
        result = find_chapter_file(chapters_dir, name)
        if result:
            _, fmt = result
            formats.add(fmt)

    if not formats:
        print(
            f"ERROR: No chapter files found in {chapters_dir}. "
            "Make sure your chapter files have a .adoc or .md extension.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(formats) > 1:
        print(
            "ERROR: Mix of .adoc and .md chapter files detected. "
            "All chapters must use the same format — choose either .adoc or .md.",
            file=sys.stderr,
        )
        sys.exit(1)

    return formats.pop()


# ---------------------------------------------------------------------------
# Jinja2 rendering
# ---------------------------------------------------------------------------

def render_template(content: str, source_label: str, variables: dict) -> str:
    """Render arbitrary text content as a Jinja2 template."""
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


try:
    from jinja2 import Undefined

    class _SilentUndefined(Undefined):
        """Return an empty string for undefined variables instead of raising an error."""
        def __str__(self) -> str:
            return ""
        def __iter__(self):
            return iter([])
        def __bool__(self) -> bool:
            return False
except ImportError:
    _SilentUndefined = None  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Markdown → AsciiDoc conversion
# ---------------------------------------------------------------------------

def _require_pypandoc() -> object:
    try:
        import pypandoc
        return pypandoc
    except ImportError:
        print(
            "ERROR: 'pypandoc' is required for Markdown chapters.\n"
            "  pip install pypandoc\n"
            "  pypandoc will also need pandoc installed on your system:\n"
            "    macOS:   brew install pandoc\n"
            "    Linux:   sudo apt install pandoc   (or sudo dnf install pandoc)\n"
            "    Windows: winget install --id JohnMacFarlane.Pandoc",
            file=sys.stderr,
        )
        sys.exit(1)


def convert_md_to_adoc(md_content: str, source_label: str) -> str:
    """
    Convert Markdown text to AsciiDoc using pypandoc.

    Pandoc maps Markdown `##` (h2) → AsciiDoc `===` (section level 2).
    In a 'book' doctype the first heading in each chapter must be level 1 (`==`).
    We shift all headings up by one level so `##` → `==`, `###` → `===`, etc.
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
        print(f"ERROR: pandoc conversion failed for {source_label}: {exc}", file=sys.stderr)
        sys.exit(1)

    # Shift heading levels: replace leading "===" with "==" etc. (max shift by 1).
    # Only do this if the file has no level-1 headings (i.e. all headings start at level 2+).
    lines = adoc.splitlines(keepends=True)
    has_level1 = any(re.match(r"^== [^=]", line) for line in lines)
    if not has_level1:
        shifted = []
        for line in lines:
            m = re.match(r"^(={2,})\s", line)
            if m:
                line = line[1:]  # strip one leading '='
            shifted.append(line)
        adoc = "".join(shifted)

    return adoc


# ---------------------------------------------------------------------------
# Logo detection
# ---------------------------------------------------------------------------

def _find_file(images_dir: Path, stem: str) -> Path | None:
    """Return the first existing file matching <stem>.svg or <stem>.png."""
    for ext in ("svg", "png"):
        candidate = images_dir / f"{stem}.{ext}"
        if candidate.exists():
            return candidate
    return None


def find_logos(images_dir: Path) -> tuple[Path | None, Path | None]:
    """
    Return (main_logo, header_logo).

    Look-up order:
      main_logo   — main_logo.svg/png  → falls back to logo.svg/png
      header_logo — header_logo.svg/png → falls back to logo.svg/png

    Either or both may be None if no suitable file is found.
    """
    generic = _find_file(images_dir, "logo")
    main_logo = _find_file(images_dir, "main_logo") or generic
    header_logo = _find_file(images_dir, "header_logo") or generic
    return main_logo, header_logo


# ---------------------------------------------------------------------------
# SVG / image Jinja2 rendering
# ---------------------------------------------------------------------------

def prepare_rendered_images(images_dir: Path, rendered_images_dir: Path, variables: dict) -> None:
    """
    Copy all images from images_dir to rendered_images_dir.
    For SVG files that contain Jinja2 directives, render them before copying.
    """
    rendered_images_dir.mkdir(parents=True, exist_ok=True)

    if not images_dir.exists():
        return

    for src in images_dir.iterdir():
        if not src.is_file():
            continue
        dst = rendered_images_dir / src.name
        if src.suffix.lower() == ".svg":
            content = src.read_text(encoding="utf-8")
            if _JINJA_PATTERN.search(content):
                rendered = render_template(content, str(src), variables)
                dst.write_text(rendered, encoding="utf-8")
            else:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Theme generation
# ---------------------------------------------------------------------------

def build_theme(main_logo: Path | None, header_logo: Path | None) -> dict:
    """
    Build an asciidoctor-pdf compatible theme.

    main_logo   — centered on the title page at 45% page width
    header_logo — right-aligned in the page header at 22% page width

    If only one logo is provided it is used for both roles but at the
    appropriate size for each context.  All paths are resolved to absolute
    so the theme works regardless of CWD at render time.
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
        "page": {
            "margin": ["0.75in", "0.67in", "0.75in", "0.67in"],
        },
        "base": {
            "font-size": 10.5,
            "line-height": 1.4,
        },
        "heading": {
            "font-style": "bold",
        },
        "code": {
            "font-size": 9,
        },
    }

    if main_ref:
        theme["title-page"] = {
            "logo": {
                "image": main_ref,
                "top": "8%",
                "align": "center",
            }
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
    rendered_chapters_dir: Path,
    chapter_names: list[str],
    rendered_images_dir: Path,
    author: str = "",
) -> str:
    lines: list[str] = []

    lines.append(f"= {title}")
    if author:
        lines.append(f":author: {author}")
    lines.append(":chapter-label:")
    lines.append(":sectnums:")
    lines.append(":reproducible:")
    lines.append(":listing-caption: Listing")
    lines.append(":source-highlighter: rouge")
    lines.append(":toc:")
    lines.append(":toclevels: 3")
    lines.append(":toc-title: Table of Contents")
    lines.append(":pdf-page-size: A4")
    lines.append(":doctype: book")
    lines.append(f":imagesdir: {rendered_images_dir.resolve()}")
    lines.append("")

    for name in chapter_names:
        adoc_file = rendered_chapters_dir / f"{name}.adoc"
        if adoc_file.exists():
            lines.append(f"include::{adoc_file.resolve()}[]")
            lines.append("")
        else:
            print(f"WARNING: Rendered chapter not found, skipping: {name}", file=sys.stderr)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# asciidoctor-pdf discovery
# ---------------------------------------------------------------------------

def find_asciidoctor_pdf() -> str:
    """Search PATH and common gem install locations for asciidoctor-pdf."""
    found = shutil.which("asciidoctor-pdf")
    if found:
        return found

    candidates: list[str] = []

    # Homebrew Ruby gem executable directory (macOS)
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

    # brew --prefix ruby fallback
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

    # ~/.gem user install (Linux / macOS gem --user-install)
    home = Path.home()
    for ver in ("4.0.0", "3.3.0", "3.2.0", "3.1.0", "3.0.0", "2.7.0"):
        candidates.append(str(home / f".gem/ruby/{ver}/bin/asciidoctor-pdf"))

    # RVM / rbenv common paths
    for rbenv_ver_dir in (home / ".rbenv/versions").glob("*/bin/asciidoctor-pdf") if (home / ".rbenv/versions").exists() else []:
        candidates.append(str(rbenv_ver_dir))

    for c in candidates:
        if Path(c).exists():
            return c

    return ""


def check_asciidoctor_pdf() -> str:
    binary = find_asciidoctor_pdf()
    if not binary:
        print(
            "ERROR: 'asciidoctor-pdf' is not installed or not in PATH.\n\n"
            "Install instructions:\n"
            "  macOS:    gem install asciidoctor-pdf\n"
            "            (if using Homebrew Ruby: $(brew --prefix ruby)/bin/gem install asciidoctor-pdf)\n"
            "  Linux:    gem install asciidoctor-pdf\n"
            "            (or: sudo apt install ruby-full && gem install asciidoctor-pdf)\n"
            "  Windows:  gem install asciidoctor-pdf\n"
            "            (requires RubyInstaller from https://rubyinstaller.org)\n\n"
            "If installed but not found, add the gem bin directory to your PATH:\n"
            "  export PATH=\"$(gem environment gemdir)/bin:$PATH\"",
            file=sys.stderr,
        )
        sys.exit(1)
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
    result = subprocess.run(cmd)
    return result.returncode


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup(paths: list[Path]) -> None:
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file():
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    cwd = Path.cwd()
    images_dir = Path(args.images).resolve() if args.images else cwd / "images"
    chapters_dir = Path(args.chapters).resolve() if args.chapters else cwd / "chapters"

    if not chapters_dir.exists():
        print(f"ERROR: Chapters directory not found: {chapters_dir}", file=sys.stderr)
        sys.exit(1)
    if not images_dir.exists():
        print(f"WARNING: Images directory not found: {images_dir} — continuing without images.", file=sys.stderr)

    config = load_config(args.config)
    validate_config(config)

    chapter_names: list[str] = config["chapters"]
    title: str = config.get("title", "Databook")
    author: str = config.get("author", "")
    jinja_vars = {k: v for k, v in config.items() if k != "chapters"}

    if args.output:
        output_pdf = Path(args.output).resolve()
    else:
        safe_title = re.sub(r"[^\w\-]", "_", title)
        output_pdf = cwd / f"{safe_title}.pdf"

    asciidoctor_bin = check_asciidoctor_pdf()

    print(f"databook-generator v{__version__}")
    print(f"Config:   {args.config}")
    print(f"Chapters: {chapters_dir}")
    print(f"Images:   {images_dir}")
    print(f"Output:   {output_pdf}")
    print()

    # Detect chapter format (.adoc or .md — no mixing)
    chapter_fmt = detect_chapter_format(chapters_dir, chapter_names)
    print(f"Chapter format: .{chapter_fmt}")

    # Logo detection
    rendered_images_dir = cwd / _RENDERED_IMAGES_DIR
    main_logo_src, header_logo_src = find_logos(images_dir)

    def _rendered(p: Path | None) -> Path | None:
        return (rendered_images_dir / p.name) if p else None

    rendered_main_logo = _rendered(main_logo_src)
    rendered_header_logo = _rendered(header_logo_src)

    if main_logo_src and header_logo_src:
        if main_logo_src == header_logo_src:
            print(f"Logo detected: {main_logo_src.name} (used for title page and header)")
        else:
            print(f"Main logo:   {main_logo_src.name}")
            print(f"Header logo: {header_logo_src.name}")
    else:
        print(
            "No logo detected. Place logo.svg/png, main_logo.svg/png, or "
            "header_logo.svg/png in the images directory."
        )

    # Build and write theme (pointing at rendered image paths)
    theme_dict = build_theme(rendered_main_logo, rendered_header_logo)
    theme_file = cwd / _THEME_FILE
    with open(theme_file, "w", encoding="utf-8") as fh:
        yaml.dump(theme_dict, fh, default_flow_style=False, allow_unicode=True)
    print(f"Theme written: {theme_file.name}")

    # Render images (copy + Jinja2 for SVGs that contain template directives)
    prepare_rendered_images(images_dir, rendered_images_dir, jinja_vars)
    print(f"Images prepared: {rendered_images_dir}")

    # Render chapters through Jinja2 (+ convert md→adoc if needed)
    rendered_chapters_dir = cwd / _RENDERED_DIR
    rendered_chapters_dir.mkdir(exist_ok=True)

    rendered_count = 0
    missing_chapters: list[str] = []

    for chapter_name in chapter_names:
        result = find_chapter_file(chapters_dir, chapter_name)
        if result is None:
            print(f"WARNING: Chapter not found, skipping: {chapter_name}.{chapter_fmt}", file=sys.stderr)
            missing_chapters.append(chapter_name)
            continue

        src_path, fmt = result
        content = src_path.read_text(encoding="utf-8")

        # Step 1: Jinja2
        rendered_content = render_template(content, str(src_path), jinja_vars)

        # Step 2: convert md → adoc if needed
        if fmt == "md":
            rendered_content = convert_md_to_adoc(rendered_content, str(src_path))

        (rendered_chapters_dir / f"{chapter_name}.adoc").write_text(rendered_content, encoding="utf-8")
        rendered_count += 1

    print(f"Rendered {rendered_count}/{len(chapter_names)} chapters.")
    if missing_chapters:
        print(f"Missing chapters: {', '.join(missing_chapters)}", file=sys.stderr)

    if rendered_count == 0:
        print("ERROR: No chapters were rendered. Aborting.", file=sys.stderr)
        cleanup([rendered_chapters_dir, rendered_images_dir, theme_file])
        sys.exit(1)

    # Assemble master .adoc
    master_adoc_path = cwd / _MASTER_ADOC
    master_content = assemble_master_adoc(
        title=title,
        rendered_chapters_dir=rendered_chapters_dir,
        chapter_names=[c for c in chapter_names if c not in missing_chapters],
        rendered_images_dir=rendered_images_dir,
        author=author,
    )
    master_adoc_path.write_text(master_content, encoding="utf-8")
    print(f"Master .adoc assembled: {master_adoc_path.name}")

    # Generate PDF
    print()
    ret = generate_pdf(master_adoc_path, theme_file, output_pdf, asciidoctor_bin)

    # Cleanup intermediates
    intermediates = [rendered_chapters_dir, rendered_images_dir, master_adoc_path, theme_file]
    if args.keep_intermediates:
        print("\nIntermediate files kept:")
        for p in intermediates:
            print(f"  {p}")
    else:
        cleanup(intermediates)

    if ret == 0:
        print(f"\nPDF generated successfully: {output_pdf}")
    else:
        print(f"\nERROR: asciidoctor-pdf exited with code {ret}.", file=sys.stderr)
        sys.exit(ret)


if __name__ == "__main__":
    main()
