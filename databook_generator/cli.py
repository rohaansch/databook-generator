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
import sys

from databook_generator import __version__
from databook_generator.builder import DatabookBuilder


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
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    try:
        builder = DatabookBuilder(
            config=args.config,
            chapters_dir=args.chapters,
            images_dir=args.images,
            output=args.output,
        )
        builder.build(keep_intermediates=args.keep_intermediates)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
