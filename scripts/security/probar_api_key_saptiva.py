"""Prueba una API key del proveedor de modelos sin imprimirla.

Usage (desde la raíz del repo, con la key en una variable de entorno):
    export SAPTIVA_API_KEY_NUEVA='...'
    apps/backend/.venv/bin/python -I scripts/security/probar_api_key_saptiva.py
    apps/backend/.venv/bin/python -I scripts/security/probar_api_key_saptiva.py --variable SAPTIVA_API_KEY

Inputs: la key en la variable indicada (por omisión SAPTIVA_API_KEY_NUEVA);
el endpoint de --base-url o de SAPTIVA_BASE_URL en envs/.env; los headers
extra (JSON, Cloudflare Access) de SAPTIVA_EXTRA_HEADERS en el entorno o en
envs/.env; el modelo del decide con --modelo.
Outputs: código HTTP y latencia de GET /v1/models y de un chat de una
palabra; cuántos modelos lista y si los del decide y la narración están.
Nunca imprime la key ni los headers: solo su longitud y los primeros 8
caracteres.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]


def _env_file(ruta: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        valores[k.strip()] = v.strip().strip("'\"")
    return valores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variable", default="SAPTIVA_API_KEY_NUEVA")
    ap.add_argument("--base-url", help="por omisión SAPTIVA_BASE_URL de envs/.env")
    ap.add_argument("--modelo", default="nemotron-3.5-lightning")
    ap.add_argument("--narrador", default="gemma-4-26b")
    ap.add_argument("--env", default=str(RAIZ / "envs" / ".env"))
    args = ap.parse_args()

    key = os.getenv(args.variable, "").strip()
    if not key:
        print(f"FALTA: la variable {args.variable} está vacía en este proceso")
        return 2
    env = _env_file(Path(args.env))
    base = (args.base_url or env.get("SAPTIVA_BASE_URL") or "https://api.saptiva.com").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    # Los headers del gateway (Cloudflare Access) pueden venir del entorno
    # del proceso, que gana sobre envs/.env.
    extra = os.getenv("SAPTIVA_EXTRA_HEADERS", "").strip() or env.get("SAPTIVA_EXTRA_HEADERS", "")
    if extra:
        try:
            headers.update({str(k): str(v) for k, v in json.loads(extra).items()})
        except json.JSONDecodeError:
            print("AVISO: SAPTIVA_EXTRA_HEADERS no es JSON; se ignora")
    print(f"key: {key[:8]}… ({len(key)} caracteres) | endpoint: {base}")
    print(f"headers extra: {sorted(k for k in headers if k != 'Authorization')}")

    ok = True
    with httpx.Client(timeout=60) as c:
        t = time.perf_counter()
        r = c.get(f"{base}/v1/models", headers=headers)
        print(f"GET /v1/models -> {r.status_code} en {time.perf_counter() - t:.1f} s")
        if r.status_code == 200:
            ids = [m.get("id") for m in r.json().get("data", [])]
            print(f"  modelos: {len(ids)}; decide {args.modelo}: {'si' if args.modelo in ids else 'NO'}; "
                  f"narrador {args.narrador}: {'si' if args.narrador in ids else 'NO'}")
            print(f"  lista: {sorted(str(i) for i in ids)}")
        else:
            ok = False
            print(f"  cuerpo: {r.text[:200]}")

        t = time.perf_counter()
        r = c.post(
            f"{base}/v1/chat/completions",
            headers=headers,
            json={
                "model": args.modelo,
                "messages": [{"role": "user", "content": "Responde solo: ok"}],
                "max_tokens": 5,
                "temperature": 0,
            },
        )
        print(f"POST chat ({args.modelo}) -> {r.status_code} en {time.perf_counter() - t:.1f} s")
        if r.status_code == 200:
            texto = r.json()["choices"][0]["message"]["content"].strip()
            print(f"  respuesta: {texto[:40]!r}")
        else:
            ok = False
            print(f"  cuerpo: {r.text[:200]}")
    print("KEY_OK" if ok else "KEY_FALLA")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
