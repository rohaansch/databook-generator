# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-04-08

### Added
- Initial release
- AsciiDoc (`.adoc`) chapter support via `asciidoctor-pdf`
- Markdown (`.md`) chapter support via `pandoc` + `pypandoc`
- Jinja2 templating in `.adoc`, `.md`, and `.svg` files
- Logo auto-detection (`logo.svg` / `logo.png`) — placed on title page and page header
- Auto-discovery of `asciidoctor-pdf` binary across Homebrew, gem user-install, rbenv, and RVM
- Per-page footer with document title and page numbers
- `--keep-intermediates` flag for debugging
- `-images`, `-chapters`, `-output` optional CLI overrides
