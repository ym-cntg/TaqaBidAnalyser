"""Where confirmed uploaded BOQs live.

Deliberately behind a small interface. The in-memory implementation is
what runs today: it needs no Unity Catalog grant, which matters because
five bid_analyzer_* tables are already waiting on exactly that grant and
a table-backed store would make this feature dead on arrival in the same
way. The cost is that uploads are lost when the app restarts, which is
acceptable for a feature shipped as BETA and stated as such in the UI.

databricks/schema/bid_analyzer_uploaded_boqs.sql holds the table design
for when the grant lands. Swapping to it means writing a
DeltaUploadStore with these same five methods and changing the one line
in get_store(); nothing that calls this module needs to change.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from backend.uploads.models import UploadedBoq


class UploadStore(ABC):
    @abstractmethod
    def get(self, project_id: str) -> UploadedBoq | None: ...

    @abstractmethod
    def put(self, boq: UploadedBoq) -> None: ...

    @abstractmethod
    def delete(self, project_id: str) -> None: ...

    @abstractmethod
    def exists(self, project_id: str) -> bool: ...

    @abstractmethod
    def project_ids(self) -> list[str]: ...


class InMemoryUploadStore(UploadStore):
    """Process-local and lock-guarded.

    The lock matters: FastAPI serves requests on a thread pool, so two
    analysts uploading to the same project at once would otherwise race
    on the same dict. It does not make the store shared across replicas;
    with more than one app instance, an upload would only be visible to
    whichever instance received it. Single-instance is the deployment
    today, and the table-backed store is the real answer to that.
    """

    def __init__(self) -> None:
        self._boqs: dict[str, UploadedBoq] = {}
        self._lock = threading.Lock()

    def get(self, project_id: str) -> UploadedBoq | None:
        with self._lock:
            return self._boqs.get(project_id)

    def put(self, boq: UploadedBoq) -> None:
        with self._lock:
            self._boqs[boq.project_id] = boq

    def delete(self, project_id: str) -> None:
        with self._lock:
            self._boqs.pop(project_id, None)

    def exists(self, project_id: str) -> bool:
        with self._lock:
            return project_id in self._boqs

    def project_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._boqs)


_STORE: UploadStore = InMemoryUploadStore()


def get_store() -> UploadStore:
    return _STORE
