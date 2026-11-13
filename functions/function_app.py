"""HTTP endpoints called by Azure Data Factory, one per ETL step.

ADF sends a JSON body such as {"month_key": 202401, "run_id": "<ADF run id>"} and records the
JSON response in its run history. A non-2xx response makes the ADF activity fail (and retry).

Keep each step short: the ADF Azure Function activity times out after about 230 seconds.
That is why each source is split into `ingest` (download -> clean -> Data Lake) and `load`
(Data Lake -> SQL staging). If a step still runs too long, convert it to a Durable Function.
"""

import json
import logging

import azure.functions as func

from etl import bts, graph, noaa
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


@app.route(route="bts/load", methods=["POST"])
def bts_load(req: func.HttpRequest) -> func.HttpResponse:
    return _run("bts_load", bts.load_month, req, _month)


@app.route(route="noaa/ingest", methods=["POST"])
def noaa_ingest(req: func.HttpRequest) -> func.HttpResponse:
    return _run("noaa_ingest", noaa.ingest_month, req, _month)


@app.route(route="noaa/load", methods=["POST"])
def noaa_load(req: func.HttpRequest) -> func.HttpResponse:
    return _run("noaa_load", noaa.load_month, req, _month)


@app.route(route="graph/load", methods=["POST"])
def graph_load(req: func.HttpRequest) -> func.HttpResponse:
    return _run("graph_load", graph.load_route_edges, req, _year)
