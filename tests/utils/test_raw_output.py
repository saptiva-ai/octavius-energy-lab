#!/usr/bin/env python3
"""Raw JSON request/response output for all clarification tests."""

import json
import httpx

URL = "http://localhost:8002/rpc"

QUERIES = [
    "datos del banco",
    "ultimo mes",
    "BANCODEMO 2024",
    "morosidad",
    "IMOR de BancoFantasma",
    "IMOR de Bank of America",
    "IMOR actual",
    "IMOR de BANCODEMO reciente",
    "evolucion del ICOR de BANCODEMO",
    "tendencia historica de morosidad",
    "compara el IMOR",
    "diferencia de morosidad",
    "IMOR y ICOR de BANCODEMO",
    "morosidad e indice de cobertura",
    "todas las metricas",
    "resumen financiero",
    "cartera de BANCODEMO",
    "indicadores de riesgo",
    "tasa de BANCODEMO",
    "clima en Cancun",
    "hola buenos dias",
    "IMOR de BANCODEMO ultimos 3 meses",
    "cartera comercial de BANCODEMO 2024",
]

def main():
    results = []

    for i, query in enumerate(QUERIES, 1):
        request = {
            "jsonrpc": "2.0",
            "id": f"test-{i:03d}",
            "method": "tools/call",
            "params": {
                "name": "bank_analytics",
                "arguments": {
                    "metric_or_query": query,
                    "mode": "dashboard"
                }
            }
        }

        print(f"{'='*80}")
        print(f"TEST {i:03d}: {query}")
        print(f"{'='*80}")
        print()
        print("REQUEST:")
        print(json.dumps(request, indent=2, ensure_ascii=False))
        print()

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(URL, json=request)
                data = response.json()
        except Exception as e:
            data = {"error": str(e)}

        print("RESPONSE:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print()
        print()

        # Extract type for analysis
        result_data = data.get("result", {}).get("content", [{}])
        if result_data and isinstance(result_data[0], dict) and "text" in result_data[0]:
            try:
                inner = json.loads(result_data[0]["text"])
                if "data" in inner:
                    inner = inner["data"]
                resp_type = inner.get("type", "data")
            except:
                resp_type = "parse_error"
        else:
            resp_type = "unknown"

        results.append({
            "query": query,
            "type": resp_type
        })

    # Analysis
    print(f"{'='*80}")
    print("ANALYSIS")
    print(f"{'='*80}")
    print()

    clarifications = [r for r in results if r["type"] == "clarification"]
    data_responses = [r for r in results if r["type"] != "clarification"]

    print(f"Total tests: {len(results)}")
    print(f"Clarifications: {len(clarifications)}")
    print(f"Data responses: {len(data_responses)}")
    print()

    print("CLARIFICATION QUERIES:")
    for r in clarifications:
        print(f"  - {r['query']}")

    print()
    print("DATA QUERIES:")
    for r in data_responses:
        print(f"  - {r['query']}")

if __name__ == "__main__":
    main()
