from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Node:
    """A single item in an ILIAS repository listing (course, folder, file, ...).

    ``obj_type`` holds ILIAS's own type code (``crs``, ``fold``, ``file``,
    ``exc``, ``frm``, ...) where it could be determined from the page.
    """

    ref_id: str
    title: str
    url: str
    obj_type: str | None = None
    description: str | None = None
