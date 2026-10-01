"""API Jouskaio.me: one modular REST API for my apps, services and personal infrastructure.

Each capability (notes synchronisation, infrastructure orchestration...) is a module
mounted under ``/api/v1/<module>``. See ``jouskaio_api.modules``.
"""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "API Jouskaio.me"

try:
    __version__ = version("jouskaio-api")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0"
