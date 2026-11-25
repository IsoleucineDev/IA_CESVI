#!/usr/bin/env python3
"""
Prueba el modelo en Ollama: ¿responde SOLO JSON y cumple las reglas de Unity?
  python test_json.py --model cesvi-json --n 20
  python test_json.py --gold        # sanity check del validador con las respuestas correctas de val.jsonl
"""
import argparse, json, time, urllib.request
from gen_dataset import validate_choque

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="cesvi-json")
ap.add_argument("--val", default="data/val.jsonl")
ap.add_argument("--n", type=int, default=20)
ap.add_argument("--host", default="http://localhost:11434")
ap.add_argument("--format-json", action="store_true", help="forzar JSON con el modo format de Ollama")
ap.add_argument("--gold", action="store_true")
a = ap.parse_args()
rows = [json.loads(l) for l in open(a.val, encoding="utf-8")][:a.n]


def ask(msgs):
    body = {"model": a.model, "messages": msgs, "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 4096}}
    if a.format_json:
        body["format"] = "json"
    req = urllib.request.Request(a.host + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=600))["message"]["content"]


ok = clean = 0
for i, r in enumerate(rows, 1):
    gold = r["messages"][2]["content"]
    t0 = time.time()
    raw = gold if a.gold else ask(r["messages"][:2])
    dt = time.time() - t0
    try:
        doc = json.loads(raw)            # estricto: sin ``` ni texto extra
        clean += 1
        errs = validate_choque(doc)
        g = json.loads(gold)
        if len(doc.get("vehiculos", [])) != len(g["vehiculos"]):
            errs.append("distinto numero de vehiculos que el esperado")
        elif [v["categoria"] for v in doc["vehiculos"]] != [v["categoria"] for v in g["vehiculos"]]:
            errs.append("categorias distintas a las esperadas")
    except Exception as e:
        errs = [f"NO es JSON limpio: {str(e)[:80]} | inicio: {raw[:60]!r}"]
    ok += not errs
    print(f"[{i:02d}/{len(rows)}] {dt:5.1f}s", "OK" if not errs else f"FALLA {errs[:3]}")
print(f"\nJSON limpio (json.loads): {clean}/{len(rows)} | cumple reglas + estructura: {ok}/{len(rows)}")
