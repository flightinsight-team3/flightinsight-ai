"""Cosmos DB NoSQL containers used by the app: asrs_reports (partition /month_key, vector
/narrative_vector) and route_summaries (partition /origin)."""

from __future__ import annotations

import os
from functools import lru_cache

from app.settings import setting

DATABASE = "flightinsight"
CONTAINER = "asrs_reports"
ROUTE_CONTAINER = "route_summaries"


@lru_cache(maxsize=1)
def _database():
    """Database client. Uses COSMOS_NOSQL_KEY if set, otherwise your `az login` identity
    (which then needs the Cosmos DB Built-in Data Contributor role on the account)."""
    from azure.cosmos import CosmosClient

    endpoint = setting("COSMOS_NOSQL_ENDPOINT")
    credential = os.getenv("COSMOS_NOSQL_KEY")
    if not credential:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
    return CosmosClient(endpoint, credential=credential).get_database_client(DATABASE)


def asrs_container():
    return _database().get_container_client(CONTAINER)


def route_container():
    return _database().get_container_client(ROUTE_CONTAINER)


def existing_ids(container) -> set[str]:
    """IDs already in the container, so a re-run can skip reports that are already embedded."""
    query = "SELECT VALUE c.id FROM c"
    return set(container.query_items(query, enable_cross_partition_query=True))
