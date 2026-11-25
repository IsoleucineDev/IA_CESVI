import json, sys, urllib.request
PORT = sys.argv[1] if len(sys.argv) > 1 else "8443"
def chat(msg, session):
    body = json.dumps({"message": msg, "stream": True, "session": session,
        "context": {"vehicles": {"V1": {}, "V2": {}}}}).encode()
    req = urllib.request.Request(f"http://localhost:{PORT}/api/ai/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))

# (respuesta del perito, qué se espera)
guion = [
  ("Alcance",                                  "pide el tipo de choque -> arranca la entrevista"),
  ("El V1 estaba detenido en el semáforo y lo golpearon por atrás", "declaracion_V1"),
  ("Saltar",                                   "declaracion_V2 omitida"),
  ("Pavimento seco",                           "superficie"),
  ("De día, buena visibilidad",                "iluminacion"),
  ("Sur a norte, carril derecho",              "sentido_carril_V1"),
  ("Sur a norte, carril derecho",              "sentido_carril_V2"),
  ("Estaba detenido, 0 km/h",                  "velocidad_V1_kmh -> 0"),
  ("Aproximadamente 45 km/h",                  "velocidad_V2_kmh -> 45"),
  ("Detenido por la luz roja",                 "maniobra_previa_V1"),
  ("Frenó al ver el semáforo",                 "maniobra_previa_V2"),
  ("Unos 15 metros",                           "distancia_previa"),
  ("Un solo impacto trasero",                  "secuencia_eventos"),
  ("Carril derecho, a 10 m del semáforo",      "punto_impacto_via"),
  ("Restos de plástico y huellas de frenado",  "evidencias_sitio"),
  ("8.5 metros",                               "huellas_frenado_m -> 8.5"),
  ("No se activaron",                          "airbags_V1"),
  ("Se activaron los frontales",               "airbags_V2"),
  ("Daño en defensa trasera, 45 cm",           "danos_V1"),
  ("Daño en defensa delantera, 50 cm",         "danos_V2"),
  ("Quedó 3 m adelante del punto de impacto",  "posicion_final_V1"),
  ("Quedó en el punto de impacto",             "posicion_final_V2"),
]
s = None
for i, (msg, esperado) in enumerate(guion, 1):
    out = chat(msg, s); s = out["session"]
    print(f"{i:>2}. PERITO: {msg}\n    IA    : {out['answer'][:95]}\n    avance: {out['progress']}%   listo: {out['ready']}   (esto responde a: {esperado})")
print("\n=== DATOS EXTRAÍDOS ===")
for k, v in s["estado"].items(): print(f"  {k}: {v!r}")
