"""Trae señales de Search Console + GA4 para uno o más términos candidatos,
como desempate al elegir la temática de la próxima nota de Nohuddle.

Uso:
    python3 fetch_signals.py "brock bowers" "bo nix" "micah parsons"
"""
import json
import os
import sys

import google.oauth2.credentials
from googleapiclient.discovery import build

BASE_DIR = os.path.dirname(__file__)
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def get_credentials():
    return google.oauth2.credentials.Credentials.from_authorized_user_file(TOKEN_FILE)


def search_console_signal(webmasters, site_url, term, days=28):
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=days)
    resp = webmasters.searchanalytics().query(
        siteUrl=site_url,
        body={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["query"],
            "dimensionFilterGroups": [{
                "filters": [{"dimension": "query", "operator": "contains", "expression": term}]
            }],
            "rowLimit": 25,
        },
    ).execute()
    rows = resp.get("rows", [])
    total_clicks = sum(r["clicks"] for r in rows)
    total_impressions = sum(r["impressions"] for r in rows)
    return {"queries_matched": len(rows), "clicks_28d": total_clicks, "impressions_28d": total_impressions}


def ga4_signal(data_api, property_id, term, days=28):
    resp = data_api.properties().runReport(
        property=f"properties/{property_id}",
        body={
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "dimensions": [{"name": "pageTitle"}],
            "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "pageTitle",
                    "stringFilter": {"matchType": "CONTAINS", "value": term, "caseSensitive": False},
                }
            },
        },
    ).execute()
    rows = resp.get("rows", [])
    pageviews = sum(int(r["metricValues"][0]["value"]) for r in rows)
    users = sum(int(r["metricValues"][1]["value"]) for r in rows)
    return {"matching_pages": len(rows), "pageviews_28d": pageviews, "active_users_28d": users}


def main():
    terms = sys.argv[1:]
    if not terms:
        print("Uso: python3 fetch_signals.py <termino1> [termino2] ...")
        sys.exit(1)

    config = load_config()
    creds = get_credentials()
    webmasters = build("webmasters", "v3", credentials=creds)
    data_api = build("analyticsdata", "v1beta", credentials=creds)

    results = {}
    for term in terms:
        sc = search_console_signal(webmasters, config["search_console_site_url"], term)
        ga = ga4_signal(data_api, config["ga4_property_id"], term)
        results[term] = {"search_console": sc, "analytics": ga}

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
