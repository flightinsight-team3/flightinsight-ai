"""HTTP endpoints called by Azure Data Factory, one per ETL step.

ADF sends a JSON body such as {"month_key": 202401, "run_id": "<ADF run id>"} and records the
JSON response in its run history. A non-2xx response makes the ADF activity fail (and retry).

Keep each step short: the ADF Azure Function activity times out after about 230 seconds.
Functions only download, clean and write parquet to the Data Lake. Loading parquet into SQL
staging is an ADF Copy activity, which is faster and has no such limit.
"""

import json
import logging

import azure.functions as func

from etl import airports, bts, graph, noaa, cosmos_sync
from etl.common import parse_month_key, parse_year

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _json(payload: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(payload), status_code=status, mimetype="application/json")


def _run(step: str, handler, req: func.HttpRequest, parse) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json({"step": step, "error": "Request body must be JSON"}, 400)
    try:
        arg = parse(body)
    except (KeyError, ValueError) as exc:
        return _json({"step": step, "error": str(exc)}, 400)

    logging.info("Starting %s for %s (ADF run %s)", step, arg, body.get("run_id"))
    try:
        result = handler(arg)
    except NotImplementedError as exc:
        return _json({"step": step, "error": f"Not implemented yet: {exc}"}, 501)
    return _json({"step": step, "status": "succeeded", **result})


def _month(body: dict) -> int:
    return parse_month_key(body["month_key"])


def _year(body: dict) -> int:
    return parse_year(body["year"])


@app.route(route="bts/ingest", methods=["POST"])
def bts_ingest(req: func.HttpRequest) -> func.HttpResponse:
    return _run("bts_ingest", bts.ingest_month, req, _month)


@app.route(route="airports/ingest", methods=["POST"])
def airports_ingest(req: func.HttpRequest) -> func.HttpResponse:
    return _run("airports_ingest", airports.ingest_month, req, _month)


@app.route(route="noaa/ingest", methods=["POST"])
def noaa_ingest(req: func.HttpRequest) -> func.HttpResponse:
    return _run("noaa_ingest", noaa.ingest_month, req, _month)


@app.route(route="noaa/load", methods=["POST"])
def noaa_load(req: func.HttpRequest) -> func.HttpResponse:
    return _run("noaa_load", noaa.load_month, req, _month)


@app.route(route="graph/load", methods=["POST"])
def graph_load(req: func.HttpRequest) -> func.HttpResponse:
    return _run("graph_load", graph.load_route_edges, req, _year)


@app.route(route="cosmos/sync", methods=["POST"])
def cosmos_sync_route(req: func.HttpRequest) -> func.HttpResponse:
    """Synchronize Azure SQL route summaries to Cosmos DB."""

    try:
        result = cosmos_sync.sync_routes_to_cosmos()

        return _json({
            "step": "cosmos_sync",
            "status": "succeeded",
            **result
        })

    except Exception:
        logging.exception("Cosmos DB synchronization failed")

        return _json({
            "step": "cosmos_sync",
            "status": "failed"
        }, 500)
