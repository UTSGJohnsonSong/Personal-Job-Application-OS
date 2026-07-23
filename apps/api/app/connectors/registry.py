from __future__ import annotations

from app.connectors.ashby import AshbyConnector
from app.connectors.base import Connector
from app.connectors.generic import GenericAtsConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.workday import WorkdayConnector

# Adding a new source = implement Connector + register here. No core changes.
_REGISTRY: dict[str, Connector] = {
    c.key: c
    for c in (
        GreenhouseConnector(),
        LeverConnector(),
        AshbyConnector(),
        GenericAtsConnector(),
        WorkdayConnector(),
    )
}


def get_connector(key: str) -> Connector:
    if key not in _REGISTRY:
        raise KeyError(f"unknown connector: {key}")
    return _REGISTRY[key]


def all_connectors() -> dict[str, Connector]:
    return dict(_REGISTRY)
