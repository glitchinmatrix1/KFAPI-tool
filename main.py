import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os

app = FastAPI(title="Kraken Futures Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

KRAKEN_BASE = "https://futures.kraken.com"
TIMEOUT = 15.0


async def kraken_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        url = KRAKEN_BASE + path
        r = await client.get(url, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=f"Kraken returned {r.status_code}: {r.text[:200]}")
        return r.json()


@app.get("/api/executions")
async def get_executions(
    symbol: str = Query(..., description="e.g. PF_XBTUSD"),
    since: Optional[int] = Query(None, description="Unix timestamp ms"),
    continuationToken: Optional[str] = Query(None),
):
    params = {"sort": "asc"}
    if since:
        params["since"] = since
    if continuationToken:
        params["continuationToken"] = continuationToken

    data = await kraken_get(f"/api/history/v2/market/{symbol}/executions", params)

    rows = []
    for el in data.get("elements", []):
        ts = el.get("timestamp")
        ev = el.get("event", {})
        exec_ev = ev.get("execution", {})
        executions = exec_ev.get("executions", [])
        if not executions and "execution" in exec_ev:
            executions = [exec_ev["execution"]]

        for ex in executions:
            maker = ex.get("makerOrder", {})
            taker = ex.get("takerOrder", {})
            rows.append({
                "time": ts,
                "uid": ex.get("uid", ""),
                "tradeable": maker.get("tradeable") or taker.get("tradeable") or "",
                "makerDirection": maker.get("direction", ""),
                "takerDirection": taker.get("direction", ""),
                "price": ex.get("price"),
                "quantity": ex.get("quantity"),
                "usdValue": ex.get("usdValue"),
                "markPrice": ex.get("markPrice"),
                "makerOrderType": maker.get("orderType", ""),
                "takerOrderType": taker.get("orderType", ""),
                "limitFilled": ex.get("limitFilled"),
            })

    return JSONResponse({
        "rows": rows,
        "continuationToken": data.get("continuationToken"),
        "total": len(rows),
    })


@app.get("/api/ohlc")
async def get_ohlc(
    symbol: str = Query(...),
    priceType: str = Query("mark", description="mark | spot | trade"),
    interval: str = Query("1m", description="1m 5m 15m 1h 4h 1d 1w"),
    fromTs: Optional[int] = Query(None, description="Unix timestamp seconds"),
    toTs: Optional[int] = Query(None, description="Unix timestamp seconds"),
):
    params = {}
    if fromTs:
        params["from"] = fromTs
    if toTs:
        params["to"] = toTs

    data = await kraken_get(f"/api/charts/v1/{priceType}/{symbol}/{interval}", params)

    candles = []
    for c in data.get("candles", []):
        candles.append({
            "time": c[0] if isinstance(c, list) else c.get("time"),
            "open":  c[1] if isinstance(c, list) else c.get("open"),
            "high":  c[2] if isinstance(c, list) else c.get("high"),
            "low":   c[3] if isinstance(c, list) else c.get("low"),
            "close": c[4] if isinstance(c, list) else c.get("close"),
            "volume": c[5] if isinstance(c, list) and len(c) > 5 else c.get("volume", 0) if isinstance(c, dict) else 0,
        })

    return JSONResponse({"candles": candles, "total": len(candles)})


@app.get("/api/markprice")
async def get_markprice(
    symbol: str = Query(...),
    since: Optional[int] = Query(None, description="Unix timestamp ms"),
    before: Optional[int] = Query(None, description="Unix timestamp ms"),
):
    params = {"sort": "asc"}
    if since:
        params["since"] = since
    if before:
        params["before"] = before

    data = await kraken_get(f"/api/history/v2/market/{symbol}/price", params)

    rows = []
    for el in data.get("elements", []):
        ts = el.get("timestamp")
        ev = el.get("event", {})
        price = (
            ev.get("markPriceChanged", {}).get("price")
            or ev.get("price")
        )
        if price is not None:
            rows.append({"timestamp": ts, "price": price})

    return JSONResponse({
        "rows": rows,
        "total": len(rows),
        "continuationToken": data.get("continuationToken"),
    })


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html") as f:
        return f.read()
