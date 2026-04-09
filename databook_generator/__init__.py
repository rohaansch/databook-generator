"""databook-generator: Generate PDF databooks from AsciiDoc or Markdown chapters with Jinja2 templating."""

from databook_generator._version import __version__, __author__, __email__
from databook_generator.builder import DatabookBuilder

__all__ = ["DatabookBuilder", "__version__", "__author__", "__email__"]
