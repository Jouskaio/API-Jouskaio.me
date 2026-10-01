"""Module registry: the one place that knows which modules exist.

Each module is one capability of the API, mounted under ``/api/v1/<name>`` (snake_case
name, kebab-case URL): ``notes_sync`` today, ``orchestrator`` (Proxmox, Docker...) and others
tomorrow. To add one: create ``modules/<name>/``, expose a ``build_module(context)``
factory, register it below, and enable it with ``JOUSKAIO_ENABLED_MODULES``.
"""

from collections.abc import Mapping

from jouskaio_api.core.module import ModuleFactory
from jouskaio_api.modules.notes_sync import build_module as build_notes_sync

MODULE_FACTORIES: Mapping[str, ModuleFactory] = {
    "notes_sync": build_notes_sync,
}
