#!/usr/bin/env python3
"""Snapshot DETERMINISTICO del portafoglio simulato per il Risk Manager.

Legge state/portfolio.json, recupera i prezzi attuali e calcola: peso % per
asset, esposizione % per categoria, liquidità % e P/L%. Stampa un report
testuale ("DATI CERTI") che l'Analista usa per applicare le regole di
diversificazione, senza dover rifare i conti.

Solo libreria standard di Python. Gira poche volte al giorno (dentro l'Analista).
⚠️ Simulazione: soldi finti. Non è consulenza finanziaria.
"""
import json
import os
import urllib.request
import urllib.parse
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORTFOLIO = ROOT / "state" / "portfolio.json"
FINNHUB_KEY = os.environ.get("MARKET_DATA_API_KEY", "")

# Le "categorie" sostituiscono i "settori" per un portafoglio multi-asset.
CATEGORIE = {
    "crypto": "Crypto",
    "us_stock": "Azioni",
    "eu_stock": "Azioni",
    "commodity": "Materie prime",
    "forex": "Valute",
}


def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def get_price(pos):
    ac = pos.get("asset_class")
    sym = pos["symbol"]
    try:
        if ac == "crypto":
            cg = pos.get("cg_id") or sym.lower()
            d = http_get_json(
                f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg)}&vs_currencies=usd"
            )
            v = d.get(cg, {}).get("usd")
            return float(v) if v else None
        if ac == "forex":
            # Cambio spot via Frankfurter (BCE, gratis). sym = 6 lettere BASEQUOTE.
            s = (sym or "").upper().replace("/", "")
            if len(s) != 6:
                return None
            base, quote = s[:3], s[3:]
            d = http_get_json(
                f"https://api.frankfurter.app/latest?from={urllib.parse.quote(base)}&to={urllib.parse.quote(quote)}"
            )
            v = d.get("rates", {}).get(quote)
            return float(v) if v else None
        # us_stock / eu_stock / commodity -> ticker quotabile su Finnhub (ETF proxy)
        if not FINNHUB_KEY:
            return None
        d = http_get_json(
            f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(sym)}&token={FINNHUB_KEY}"
        )
        return float(d["c"]) if d.get("c") else None
    except Exception:
        return None


def main():
    p = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    cfg = p.get("config", {})
    cur = cfg.get("currency", "USD")
    cash = p.get("cash", 0.0)
    positions = p.get("open_positions", [])

    rows = []
    invested = 0.0
    for pos in positions:
        price = get_price(pos)
        entry = pos.get("entry_price") or 0
        amount = pos.get("amount", 0)
        sign = 1 if pos.get("direction", "long") == "long" else -1
        pnl = sign * (price - entry) / entry * amount if (price and entry) else 0.0
        value = amount + pnl
        invested += value
        rows.append({
            "symbol": pos["symbol"],
            "categoria": CATEGORIE.get(pos.get("asset_class"), "Altro"),
            "value": value,
            "pnl_pct": (pnl / amount * 100 if amount else 0.0),
            "price": price,
        })

    equity = cash + invested
    cash_pct = cash / equity * 100 if equity else 0.0
    cat = {}
    for r in rows:
        r["weight"] = r["value"] / equity * 100 if equity else 0.0
        cat[r["categoria"]] = cat.get(r["categoria"], 0.0) + r["weight"]

    out = []
    out.append("=== REPORT MATEMATICO PORTAFOGLIO (DATI CERTI — non ricalcolare) ===")
    out.append(f"Valore totale portafoglio: {equity:,.2f} {cur}")
    out.append(f"Liquidita (cash): {cash:,.2f} {cur} ({cash_pct:.1f}%)")
    out.append("")
    out.append("ALLOCAZIONE PER ASSET:")
    if rows:
        for r in rows:
            pr = f"${r['price']:,.2f}" if r["price"] else "n/d"
            out.append(
                f"- {r['symbol']} [{r['categoria']}]: peso {r['weight']:.1f}% | "
                f"valore {r['value']:,.2f} {cur} | P/L {r['pnl_pct']:+.1f}% | prezzo {pr}"
            )
    else:
        out.append("- (nessuna posizione aperta)")
    out.append("")
    out.append("ALLOCAZIONE PER CATEGORIA:")
    if cat:
        for c, w in sorted(cat.items(), key=lambda x: -x[1]):
            out.append(f"- {c}: {w:.1f}%")
    else:
        out.append("- (vuoto)")
    print("\n".join(out))


if __name__ == "__main__":
    main()
