from __future__ import annotations

from app.connectors.ashby import AshbyConnector
from app.connectors.bamboohr import BambooHrConnector
from app.connectors.base import Connector
from app.connectors.generic import GenericAtsConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.jsonld import JsonLdCareerConnector
from app.connectors.lever import LeverConnector
from app.connectors.oracle_orc import OracleOrcConnector
from app.connectors.sitemap import SitemapCareerConnector
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.successfactors import SuccessFactorsConnector
from app.connectors.user_import import UserImportConnector
from app.connectors.workday import WorkdayConnector

# Adding a source = implement Connector + register here + add a catalog entry
# in app/sources/catalog.py. No change to ingestion, eligibility or ranking.
_REGISTRY: dict[str, Connector] = {
    c.key: c
    for c in (
        # First-party applicant tracking systems
        GreenhouseConnector(),
        LeverConnector(),
        AshbyConnector(),
        SmartRecruitersConnector(),
        WorkdayConnector(),
        OracleOrcConnector(),
        BambooHrConnector(),
        SuccessFactorsConnector(),
        # Generic employer career pages
        JsonLdCareerConnector(),
        SitemapCareerConnector(),
        GenericAtsConnector(),
        # Account-bound sources: user supplies the data, we never log in
        UserImportConnector(),
    )
}


def get_connector(key: str) -> Connector:
    if key not in _REGISTRY:
        raise KeyError(f"unknown connector: {key}")
    return _REGISTRY[key]


def all_connectors() -> dict[str, Connector]:
    return dict(_REGISTRY)
