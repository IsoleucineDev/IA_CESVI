#!/usr/bin/env python3
"""
gen_dataset.py - Dataset sintético (ChatML/messages) para fine-tuning:
    hechos periciales (texto)  ->  choque.json válido para Unity.

La salida JSON se CONSTRUYE por código (cada regla se cumple por construcción)
y se verifica con validate_choque() antes de escribirse. El texto de entrada se
genera desde los MISMOS datos, así que texto y JSON siempre son consistentes.

Uso:
    python gen_dataset.py --n 1000 --seed 7 --out data
Salida: data/train.jsonl  data/val.jsonl
Importable: from gen_dataset import validate_choque, SYSTEM_PROMPT
"""
import argparse, json, math, random, re
from copy import deepcopy
from pathlib import Path

G = 9.81
CATALOGO = ["sedan", "hatchback", "suv", "pickup", "deportivo", "van", "limusina",
            "ambulancia", "bomberos", "autobus", "camion", "tractocamion", "semirremolque"]
PREFIJOS = {"poste": "obstaculo", "semaforo": "senalizacion", "senal": "senalizacion",
            "roca": "obstaculo", "animal": "obstaculo", "indicio": "indicio", "objeto": "obstaculo"}
PROHIBIDAS = ("impacto", "choque", "colision", "caida")
SNAKE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")

SYSTEM_PROMPT = (
    "Eres el motor de extraccion de CESVI. Recibes hechos periciales verificados y devuelves "
    "SOLO un objeto JSON valido (UTF-8, punto decimal, sin comentarios, sin texto extra, sin ```) "
    "con el esquema de reconstruccion para Unity: metadata, escena (origen_geografico, condiciones), "
    "impacto, vehiculos, elementos_estaticos, registro_impactos. "
    "Reglas: ids vehiculo_N en orden de aparicion; categoria exacta de {" + ",".join(CATALOGO) + "}; "
    "categoria, fase e id en minusculas, sin acentos, snake_case. "
    "Ejes en escena/vehiculos/estaticos: x=Este, y=Arriba (0 en terreno), z=Norte. "
    "En impacto.posicion: x=Este, y=Norte, z=0. rotacion_grados.y = rumbo - 180. "
    "Minimo 2 keyframes por vehiculo ordenados por tiempo_s, cerrando con 2 keyframes identicos en "
    "detencion_posicion_final. Nunca uses impacto, choque, colision o caida en fases previas al golpe real. "
    "Estaticos: <prefijo>_<n> con prefijo poste|semaforo|senal|roca|animal|indicio|objeto; "
    "poste/semaforo/senal usan escala.y = altura en metros; indicio usa escala.y = 0.03. "
    "Marca datos aproximados con estimado / masa_estimada / mu_estimado = true. No inventes datos."
)

# ----------------------------------------------------------------- catálogos
FLOTA = {  # modelo, largo, ancho, alto, masa_kg
    "sedan": [("Nissan Tsuru 2010", 4.2, 1.57, 1.38, 950), ("Volkswagen Jetta 2016", 4.64, 1.78, 1.46, 1300),
              ("Nissan Versa 2018", 4.46, 1.69, 1.5, 1050), ("Chevrolet Aveo 2014", 4.4, 1.7, 1.5, 1100)],
    "hatchback": [("Nissan March 2015", 3.78, 1.66, 1.52, 950), ("Volkswagen Gol 2012", 3.89, 1.64, 1.46, 950),
                  ("Kia Rio 2019", 4.07, 1.72, 1.45, 1100)],
    "suv": [("Mazda CX-5 2019", 4.55, 1.84, 1.68, 1600), ("Toyota RAV4 2018", 4.6, 1.85, 1.69, 1650),
            ("Honda CR-V 2017", 4.59, 1.85, 1.68, 1600)],
    "pickup": [("Nissan NP300 2017", 5.2, 1.85, 1.8, 1700), ("Toyota Hilux 2019", 5.3, 1.86, 1.81, 2000),
               ("Chevrolet S10 2015", 5.3, 1.8, 1.7, 1800)],
    "deportivo": [("Ford Mustang 2016", 4.78, 1.92, 1.38, 1700), ("Chevrolet Camaro 2015", 4.78, 1.9, 1.35, 1700)],
    "van": [("Volkswagen Combi 1990", 4.5, 1.72, 1.95, 1200), ("Nissan Urvan 2016", 5.2, 1.69, 1.98, 1900),
            ("Toyota Hiace 2018", 5.38, 1.88, 2.28, 2100)],
    "limusina": [("Lincoln Town Car limusina 2008", 9.0, 2.0, 1.5, 3200)],
    "ambulancia": [("Ford Transit ambulancia 2017", 5.98, 2.06, 2.5, 3200)],
    "bomberos": [("Pierce camion de bomberos 2010", 9.5, 2.5, 3.4, 15000)],
    "autobus": [("Mercedes-Benz O500 2012", 12.0, 2.55, 3.3, 14000)],
    "camion": [("Isuzu ELF 2015", 6.5, 2.1, 2.8, 5500), ("Hino 300 2016", 6.8, 2.2, 2.9, 5800)],
    "tractocamion": [("Kenworth T800 2014", 7.2, 2.6, 3.9, 8500), ("Freightliner Cascadia 2016", 7.0, 2.6, 3.9, 8000)],
    "semirremolque": [("Caja seca 48 pies", 14.6, 2.6, 4.1, 6500)],
}
DISP = {"sedan": ["sedán", "auto sedán"], "hatchback": ["hatchback", "auto compacto hatchback"],
        "suv": ["SUV", "camioneta SUV"], "pickup": ["pick-up", "camioneta pickup"], "deportivo": ["deportivo"],
        "van": ["van", "vagoneta"], "limusina": ["limusina"], "ambulancia": ["ambulancia"],
        "bomberos": ["camión de bomberos"], "autobus": ["autobús"], "camion": ["camión rígido", "camión de carga"],
        "tractocamion": ["tractocamión"], "semirremolque": ["semirremolque", "caja del remolque"]}
FASE_TXT = {
    "aproximacion": ["aproximación", "circulación normal previa", "avance previo"],
    "estacionado": ["estacionado", "detenido (estacionado)"],
    "preparacion_maniobra": ["preparación de maniobra", "inicio de maniobra de reversa"],
    "reversa": ["reversa", "maniobra en reversa"],
    "percepcion_animal": ["percepción del animal", "el conductor ve al animal"],
    "percepcion_obstaculo": ["percepción del obstáculo", "el conductor ve el bache"],
    "frenado_de_emergencia": ["frenado de emergencia", "frenado previo al choque", "frenado antes del golpe"],
    "evasion": ["evasión", "maniobra evasiva para evitar el choque", "volantazo evasivo"],
    "impacto_inicial": ["impacto inicial", "primer contacto", "momento del impacto"],
    "caida_en_bache": ["caída en bache", "el vehículo cae en el bache"],
    "rotacion_poscolision": ["rotación poscolisión", "giro tras el golpe"],
    "desplazamiento_post_impacto": ["desplazamiento posterior al impacto", "deslizamiento tras el golpe"],
    "detencion_posicion_final": ["detención en posición final", "reposo final"],
}
LUGARES = [  # municipio, estado, lat, lon, altura
    ("Toluca", "Estado de México", 19.2826, -99.6557, 2660), ("Metepec", "Estado de México", 19.2540, -99.6040, 2610),
    ("Querétaro", "Querétaro", 20.5888, -100.3899, 1820), ("Ciudad de México", "Ciudad de México", 19.4326, -99.1332, 2240),
    ("Monterrey", "Nuevo León", 25.6866, -100.3161, 540), ("Guadalajara", "Jalisco", 20.6597, -103.3496, 1560),
    ("Puebla", "Puebla", 19.0414, -98.2063, 2135), ("León", "Guanajuato", 21.1250, -101.6860, 1815),
    ("Mérida", "Yucatán", 20.9674, -89.5926, 10), ("Tijuana", "Baja California", 32.5149, -117.0382, 20),
    ("Cuernavaca", "Morelos", 18.9242, -99.2216, 1510),
]
CALLES = ["Av. Paseo Tollocan", "Bernardo Quintana esquina Acceso III", "Blvd. Aeropuerto", "Av. Las Torres",
          "Calzada de Tlalpan", "Carretera Toluca-Naucalpan km 12", "Av. Universidad", "Periférico Norte",
          "Blvd. Díaz Ordaz", "Carretera federal 57 km 85", "Av. Juárez esquina Calle 5", "Calle 60 esquina 33",
          "Av. Insurgentes Sur", "Libramiento Poniente km 3"]
CARD8 = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
CARD_LONG = dict(zip(CARD8, ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]))
CARD_TXT = dict(zip(CARD8, ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]))


# ----------------------------------------------------------------- utilidades
def rnd(x, n=2):
    v = round(float(x), n)
    return 0.0 if v == 0 else v


def kmh(v):
    return v / 3.6


def dirvec(h):  # (este, norte) de un rumbo medido desde el norte, horario
    a = math.radians(h)
    return math.sin(a), math.cos(a)


def hnorm(h):
    return rnd(rnd(h, 1) % 360, 1)


def card(h):
    return CARD8[int(((h % 360) + 22.5) // 45) % 8]


def rumbo_random(axis_only=False):
    if axis_only:
        return random.choice([0, 90, 180, 270])
    return random.choice([random.choice(range(0, 360, 45)), random.randint(0, 359)])


def pick_veh(cats):
    cat = random.choice(cats)
    m = random.choice(FLOTA[cat])
    k = random.uniform(0.98, 1.02)
    return dict(cat=cat, modelo=m[0], largo=rnd(m[1] * k), ancho=rnd(m[2] * k), alto=rnd(m[3] * k),
                masa=int(round(m[4] * random.uniform(0.95, 1.1), -1)), masa_est=random.random() < 0.6)


# ----------------------------------------------------------------- cinemática
def brake_speed(v0, tb, a):
    return lambda t: v0 if t < tb else max(v0 - a * (t - tb), 0.0)


def pre_frames(spec, speed, t_imp, mdir, center, bhead, lat=None):
    """spec: [(fase, t, est, dhead)] -> frames con posición reconstruida hacia atrás desde el impacto."""
    def s(t):
        n = 200
        dt = (t_imp - t) / n
        return sum(speed(t + (i + 0.5) * dt) for i in range(n)) * dt
    dx, dn = dirvec(mdir)
    px, pn = dirvec(mdir + 90)
    out = []
    for fase, t, est, dh in spec:
        d = s(t)
        l = lat(t) if lat else 0.0
        out.append(dict(t=t, fase=fase, e=center[0] - dx * d + px * l, n=center[1] - dn * d + pn * l,
                        head=bhead + dh, v=speed(t) * 3.6, est=est))
    return out


def post_frames(t_imp, center, v_post_kmh, slide_head, mu, head_imp, fases, final_head):
    v = kmh(v_post_kmh)
    a = min(mu * G * random.uniform(0.25, 0.9), v / 0.9)
    ts = v / a
    dx, dn = dirvec(slide_head)
    pos = lambda tau: (center[0] + dx * (v * tau - 0.5 * a * tau * tau), center[1] + dn * (v * tau - 0.5 * a * tau * tau))
    out, k = [], len(fases)
    for i, f in enumerate(fases):
        tau = ts * (i + 1) / (k + 1)
        e, n = pos(tau)
        out.append(dict(t=t_imp + tau, fase=f, e=e, n=n, head=head_imp + (final_head - head_imp) * (i + 1) / (k + 1),
                        v=(v - a * tau) * 3.6, est=random.random() < 0.6))
    e, n = pos(ts)
    out.append(dict(t=t_imp + ts, fase="detencion_posicion_final", e=e, n=n, head=final_head, v=0.0, est=False))
    return out


def center_at_impact(d, half, sign=-1):
    return (sign * d[0] * half, sign * d[1] * half)


def mk_vehicle(etq, base, frames, dwell=None, **extra):
    v = dict(base)
    v.update(etq=etq, frames=frames, dwell=dwell or random.choice([2, 3, 4]), **extra)
    return v


# ----------------------------------------------------------------- escenarios
def sc_alcance(tracto=False):
    h = rumbo_random(tracto)
    d = dirvec(h)
    A = pick_veh(["tractocamion"] if tracto else ["sedan", "hatchback", "suv", "pickup", "van", "camion", "autobus", "deportivo"])
    B = pick_veh(["sedan", "hatchback", "suv", "pickup", "van"])
    parked = random.random() < 0.35
    vB = 0.0 if parked else kmh(random.uniform(8, 30))
    t_imp = rnd(random.uniform(4, 8), 1)
    vi = vB + kmh(random.uniform(10, 35))
    vA0 = max(vi + kmh(random.uniform(0, 25)), kmh(40))
    tb = rnd(t_imp - random.uniform(1.2, 2.4), 1)
    a = (vA0 - vi) / (t_imp - tb)
    cA, cB = center_at_impact(d, A["largo"] / 2), center_at_impact(d, B["largo"] / 2, +1)
    fa = pre_frames([("aproximacion", 0.0, False, 0), ("frenado_de_emergencia", tb, random.random() < 0.5, 0),
                     ("impacto_inicial", t_imp, False, 0)], brake_speed(vA0, tb, a), t_imp, h, cA, h)
    fb = pre_frames([("estacionado" if parked else "aproximacion", 0.0, False, 0), ("impacto_inicial", t_imp, False, 0)],
                    lambda t: vB, t_imp, h, cB, h)
    vp = (A["masa"] * vi + B["masa"] * vB) / (A["masa"] + B["masa"])
    dhA = 0 if tracto else random.choice([-1, 1]) * random.uniform(0, 15)
    dhB = random.choice([-1, 1]) * random.uniform(0, 25)
    mu = random.uniform(0.4, 0.75)
    ph = lambda dh: (["rotacion_poscolision"] if abs(dh) > 10 else []) + ["desplazamiento_post_impacto"]
    fa += post_frames(t_imp, cA, max(vp * 0.9 * 3.6, 10), h + dhA / 2, mu, h, ph(dhA), h + dhA)
    fb += post_frames(t_imp, cB, max(vp * 1.15 * 3.6, 12), h + dhB / 2, mu, h, ph(dhB), h + dhB)
    vehs = [mk_vehicle("A", A, fa)]
    if tracto:
        T = pick_veh(["semirremolque"])
        off = rnd(A["largo"] / 2 + T["largo"] / 2 - 1.0, 1)
        ft = deepcopy(fa)
        for f in ft:
            f["e"] -= d[0] * off
            f["n"] -= d[1] * off
        vehs.append(mk_vehicle("A-R", T, ft, dwell=None, trailer_off=off))
        vehs[-1]["dwell"] = vehs[0]["dwell"]
    vehs.append(mk_vehicle("B", B, fb))
    vehs[-1]["dwell"] = random.choice([2, 3, 4])
    ia, ib = 0, len(vehs) - 1
    statics = []
    if random.random() < 0.5:
        statics.append(dict(pref="indicio", desc="Fragmentos de vidrio", e=random.uniform(-1.2, 1.2), n=random.uniform(-1.2, 1.2),
                            w=2.0, l=1.5))
    imp = dict(t=t_imp, tipo="alcance_a_vehiculo_estacionado" if parked else "alcance", idp="colision",
               h=rnd(random.uniform(0.4, 0.9), 1), part=[(ia, "frontal"), (ib, "trasera")])
    return vehs, statics, [imp], h


def sc_reversa():
    hA = rumbo_random()
    m = (hA + 180) % 360
    d = dirvec(m)
    A = pick_veh(["sedan", "hatchback", "suv", "pickup", "van", "camion"])
    B = pick_veh(["sedan", "hatchback", "suv", "pickup", "van"])
    t_imp = rnd(random.uniform(3, 6), 1)
    vi = kmh(random.uniform(4, 12))
    tm = 1.0
    cA, cB = center_at_impact(d, A["largo"] / 2), center_at_impact(d, B["ancho"] / 2, +1)
    fa = pre_frames([("preparacion_maniobra", 0.0, False, 0), ("reversa", rnd(tm + random.uniform(0.8, 1.6), 1), random.random() < 0.5, 0),
                     ("impacto_inicial", t_imp, False, 0)], lambda t: 0.0 if t < tm else vi, t_imp, m, cA, hA)
    side = random.choice([90, 270])
    hB = (m + side) % 360
    fb = pre_frames([("estacionado", 0.0, False, 0), ("impacto_inicial", t_imp, False, 0)], lambda t: 0.0, t_imp, m, cB, hB)
    mu = random.uniform(0.4, 0.75)
    fa += post_frames(t_imp, cA, max(vi * 3.6 * 0.3, 6), m, mu, hA, ["desplazamiento_post_impacto"], hA)
    dhB = random.uniform(-5, 5)
    fb += post_frames(t_imp, cB, max(vi * 3.6 * 0.6, 8), m, mu, hB, ["desplazamiento_post_impacto"], hB + dhB)
    vehs = [mk_vehicle("A", A, fa), mk_vehicle("B", B, fb)]
    zona = "lateral_derecha" if side == 90 else "lateral_izquierda"
    imp = dict(t=t_imp, tipo="colision_de_reversa_contra_vehiculo_estacionado", idp="colision",
               h=rnd(random.uniform(0.4, 0.8), 1), part=[(0, "trasera"), (1, zona)])
    return vehs, [], [imp], hA


def sc_cruce():
    hA = rumbo_random()
    side = random.choice([90, 270])
    hB = (hA + side) % 360
    dA, dB = dirvec(hA), dirvec(hB)
    A = pick_veh(["sedan", "hatchback", "suv", "pickup", "van", "deportivo", "camion"])
    B = pick_veh(["sedan", "hatchback", "suv", "pickup", "van", "autobus"])
    t_imp = rnd(random.uniform(3, 7), 1)
    viA = kmh(random.uniform(25, 60))
    vA0 = viA + kmh(random.uniform(0, 20))
    brakes = random.random() < 0.7
    tb = rnd(t_imp - random.uniform(0.8, 1.8), 1) if brakes else t_imp + 1
    a = (vA0 - viA) / max(t_imp - tb, 0.1) if brakes else 0
    vB = kmh(random.uniform(25, 50))
    cA = center_at_impact(dA, A["largo"] / 2)
    cB = (dA[0] * B["ancho"] / 2, dA[1] * B["ancho"] / 2)
    specA = [("aproximacion", 0.0, False, 0)] + ([("frenado_de_emergencia", tb, random.random() < 0.5, 0)] if brakes else []) + \
            [("impacto_inicial", t_imp, False, 0)]
    fa = pre_frames(specA, brake_speed(vA0, tb, a), t_imp, hA, cA, hA)
    fb = pre_frames([("aproximacion", 0.0, False, 0), ("impacto_inicial", t_imp, False, 0)], lambda t: vB, t_imp, hB, cB, hB)
    mu = random.uniform(0.4, 0.75)
    dhA = random.choice([-1, 1]) * random.uniform(0, 20)
    sB = 1 if side == 90 else -1
    dhB = sB * random.uniform(25, 70)
    vpB = max(A["masa"] * viA / (A["masa"] + B["masa"]) * 3.6 * 0.8, 12)
    ph = lambda dh: (["rotacion_poscolision"] if abs(dh) > 10 else []) + ["desplazamiento_post_impacto"]
    fa += post_frames(t_imp, cA, max(viA * 3.6 * 0.45, 10), hA + dhA / 2, mu, hA, ph(dhA), hA + dhA)
    fb += post_frames(t_imp, cB, vpB, hA, mu, hB, ["rotacion_poscolision", "desplazamiento_post_impacto"], hB + dhB)
    vehs = [mk_vehicle("A", A, fa), mk_vehicle("B", B, fb)]
    zona = "lateral_derecha" if side == 90 else "lateral_izquierda"
    imp = dict(t=t_imp, tipo="colision_lateral_en_crucero", idp="colision", h=rnd(random.uniform(0.5, 0.9), 1),
               part=[(0, "frontal"), (1, zona)])
    return vehs, [], [imp], hA


def sc_fijo(var):
    h = rumbo_random()
    d = dirvec(h)
    A = pick_veh(["sedan", "hatchback", "suv", "pickup", "van", "camion", "autobus", "deportivo", "ambulancia", "limusina", "bomberos"])
    cA = center_at_impact(d, A["largo"] / 2)
    mu = random.uniform(0.4, 0.75)
    statics = []
    if var == "poste":
        t_imp = rnd(random.uniform(4, 8), 1)
        vi = kmh(random.uniform(20, 60))
        vA0 = vi + kmh(random.uniform(0, 25))
        brakes = random.random() < 0.6
        tb = rnd(t_imp - random.uniform(1.0, 2.2), 1) if brakes else t_imp + 1
        a = (vA0 - vi) / max(t_imp - tb, 0.1) if brakes else 0
        spec = [("aproximacion", 0.0, False, 0)] + ([("frenado_de_emergencia", tb, random.random() < 0.5, 0)] if brakes else []) + \
               [("impacto_inicial", t_imp, False, 0)]
        fa = pre_frames(spec, brake_speed(vA0, tb, a), t_imp, h, cA, h)
        statics.append(dict(pref="poste", desc="Poste de alumbrado", e=0.0, n=0.0, alt=random.choice([6, 7, 8, 9, 10])))
        tipo, idp, zona, phase_imp = "choque_contra_objeto_fijo", "choque", random.choice(["frontal", "frontal_derecha", "frontal_izquierda"]), "impacto_inicial"
        post_ph = ["desplazamiento_post_impacto"]
        vpost = max(vi * 3.6 * 0.2, 8)
    else:
        bache = var == "bache"
        t_imp = rnd(random.uniform(5.5, 9), 1)
        t_perc = rnd(t_imp - random.uniform(3.0, 4.0), 1)
        tb = rnd(t_perc + random.uniform(0.6, 1.2), 1)
        te = rnd(tb + random.uniform(0.3, 0.8), 1)
        vi = kmh(random.uniform(25, 60))
        vA0 = vi + kmh(random.uniform(15, 35))
        a = (vA0 - vi) / (t_imp - tb)
        Lmax = random.choice([-1, 1]) * rnd(random.uniform(1.5, 3.0), 1)
        lat = lambda t: Lmax if t < te else Lmax * (1 - (t - te) / (t_imp - te))
        ang = random.uniform(6, 14)
        dh_ev = -ang if Lmax > 0 else ang
        fase_perc = "percepcion_obstaculo" if bache else "percepcion_animal"
        phase_imp = "caida_en_bache" if bache else "impacto_inicial"
        spec = [("aproximacion", 0.0, False, 0), (fase_perc, t_perc, random.random() < 0.5, 0),
                ("frenado_de_emergencia", tb, random.random() < 0.5, 0), ("evasion", te, True, dh_ev), (phase_imp, t_imp, False, 0)]
        fa = pre_frames(spec, brake_speed(vA0, tb, a), t_imp, h, cA, h, lat)
        if bache:
            statics.append(dict(pref="indicio", desc="Bache", e=0.0, n=0.0, w=1.2, l=1.0))
            tipo, idp, zona = "caida_en_bache_tras_maniobra_evasiva", "caida", "frontal_inferior"
            vpost = max(vi * 3.6 * 0.6, 10)
        else:
            statics.append(dict(pref="roca", desc="Roca", e=0.0, n=0.0, w=1.2, alt=0.8, l=1.0))
            # animal sobre la línea inicial del carril, adelante del vehículo al percibirlo
            sp = (fa[1]["e"] - cA[0] - dirvec(h + 90)[0] * Lmax, fa[1]["n"] - cA[1] - dirvec(h + 90)[1] * Lmax)
            dist_p = -(sp[0] * d[0] + sp[1] * d[1])  # distancia a lo largo de la marcha antes del impacto
            gap = min(random.uniform(10, 22), dist_p * 0.8)
            px, pn = dirvec(h + 90)
            statics.append(dict(pref="animal", desc=random.choice(["Perro", "Vaca", "Caballo"]),
                                e=cA[0] - d[0] * (dist_p - gap) + px * Lmax, n=cA[1] - d[1] * (dist_p - gap) + pn * Lmax,
                                w=0.5, alt=0.9, l=1.2))
            tipo, idp, zona = "choque_contra_objeto_fijo", "choque", random.choice(["frontal", "frontal_derecha", "frontal_izquierda"])
            vpost = max(vi * 3.6 * 0.2, 8)
        post_ph = ["desplazamiento_post_impacto"]
    dh = random.uniform(-10, 10)
    fa += post_frames(t_imp, cA, vpost, h + dh / 2, mu, h, post_ph, h + dh)
    imp = dict(t=t_imp, tipo=tipo, idp=idp, h=rnd(random.uniform(0.3, 0.8), 1), part=[(0, zona)])
    return [mk_vehicle("A", A, fa)], statics, [imp], h


def background(statics):
    for _ in range(random.choice([0, 0, 1, 1, 2])):
        pref = random.choice(["poste", "semaforo", "senal", "objeto"])
        e, n = random.choice([-1, 1]) * random.uniform(6, 25), random.choice([-1, 1]) * random.uniform(6, 25)
        if pref == "poste":
            statics.append(dict(pref="poste", desc="Poste de alumbrado", e=e, n=n, alt=random.choice([7, 8, 9])))
        elif pref == "semaforo":
            statics.append(dict(pref="semaforo", desc="Semáforo", e=e, n=n, alt=5.5))
        elif pref == "senal":
            statics.append(dict(pref="senal", desc=random.choice(["Señal de alto", "Señal de velocidad máxima 40", "Señal de ceda el paso"]),
                                e=e, n=n, alt=2.5))
        else:
            statics.append(dict(pref="objeto", desc="Cono vial", e=e, n=n, w=0.4, alt=0.7, l=0.4))


# ----------------------------------------------------------------- escena / JSON
def make_scene(h):
    lug = random.choice(LUGARES)
    lat = rnd(lug[2] + random.uniform(-0.03, 0.03), 7)
    lon = rnd(lug[3] + random.uniform(-0.03, 0.03), 7)
    clima = random.choices(["despejado", "nublado", "lluvia", "niebla"], [5, 2, 2, 1])[0]
    sup = random.choices(["asfalto", "concreto", "terraceria", "grava"], [6, 2, 1, 1])[0]
    base = {"asfalto": 0.7, "concreto": 0.75, "terraceria": 0.55, "grava": 0.5}[sup]
    if clima == "lluvia" and sup in ("asfalto", "concreto"):
        base *= 0.65
    carr = random.choice([1, 2, 3])
    ac = random.choice([3.0, 3.3, 3.5, 3.65])
    cond = dict(clima=clima, superficie=sup, iluminacion=random.choice(["diurna", "nocturna"]),
                coeficiente_friccion_mu=rnd(base + random.uniform(-0.05, 0.05)), mu_estimado=random.random() < 0.6,
                sentido_circulacion=CARD_LONG[card(h)])
    if random.random() > 0.25:
        cond["carriles_por_sentido"] = carr
    if random.random() > 0.25:
        cond["ancho_calle_m"], cond["ancho_carril_m"] = rnd(carr * 2 * ac, 1), ac
    if random.random() > 0.25:
        cond["limite_velocidad_kmh"] = random.choice([30, 40, 50, 60, 80, 90])
    est = random.random() < 0.4
    geo = dict(latitud=lat, longitud=lon)
    if random.random() > 0.3:
        geo["altura"] = lug[4]
    geo["estimado"] = est
    geo["nota"] = "Obtenida de Google Maps" if est else "Tomada en sitio con GPS"
    exp = random.choice([f"{random.randint(10000, 29999)}-{random.randint(1000000, 9999999)}", f"EXP-{random.randint(1, 999):03d}"])
    off = (rnd(random.uniform(-4, 4), 1), rnd(random.uniform(-4, 4), 1)) if random.random() < 0.6 else (0.0, 0.0)
    return dict(lug=lug, calle=random.choice(CALLES), geo=geo, cond=cond, exp=exp, off=off)


def P(e, n, y=0.0):
    return {"x": rnd(e), "y": rnd(y), "z": rnd(n)}


def static_json(s, counters):
    counters[s["pref"]] = counters.get(s["pref"], 0) + 1
    p = s["pref"]
    if p == "poste":
        esc = {"x": 0.3, "y": s["alt"], "z": 0.3}
    elif p == "semaforo":
        esc = {"x": 0.4, "y": s["alt"], "z": 0.4}
    elif p == "senal":
        esc = {"x": 0.1, "y": s["alt"], "z": 0.1}
    elif p == "indicio":
        esc = {"x": s["w"], "y": 0.03, "z": s["l"]}
    else:
        esc = {"x": s["w"], "y": s["alt"], "z": s["l"]}
    return {"id": f"{p}_{counters[p]}", "tipo": PREFIJOS[p], "descripcion": s["desc"],
            "transform": {"posicion": P(s["e"], s["n"]), "escala": esc}}


def build_json(scene, vehs, statics, impacts):
    geo, cond = scene["geo"], scene["cond"]
    doc = {"metadata": {"version": "2.1.0", "expediente": scene["exp"]},
           "escena": {"nombre": scene["calle"], "municipio": scene["lug"][0], "estado": scene["lug"][1], "pais": "México",
                      "origen_geografico": geo, "condiciones": cond},
           "impacto": {"posicion": {"x": scene["off"][0], "y": scene["off"][1], "z": 0}},
           "vehiculos": [], "elementos_estaticos": [], "registro_impactos": []}
    for i, v in enumerate(vehs, 1):
        fr = []
        for f in v["frames"]:
            fr.append({"tiempo_s": rnd(f["t"]), "fase": f["fase"], "posicion": P(f["e"], f["n"]),
                       "rotacion_grados": {"x": 0, "y": rnd(hnorm(f["head"]) - 180, 1), "z": 0},
                       "velocidad_kmh": rnd(f["v"], 1), "estimado": bool(f["est"])})
        fr[0]["es_posicion_inicial"] = True
        last = deepcopy(fr[-1])
        last["tiempo_s"] = rnd(last["tiempo_s"] + v["dwell"])
        fr.append(last)
        h0 = hnorm(v["frames"][0]["head"])
        doc["vehiculos"].append({
            "id": f"vehiculo_{i}", "etiqueta": v["etq"], "categoria": v["cat"], "modelo": v["modelo"],
            "direccion_cardinal_capturada": card(h0), "rumbo_capturado_grados": h0,
            "transform_inicial": {"posicion": fr[0]["posicion"], "rotacion_grados": fr[0]["rotacion_grados"]},
            "dimensiones_m": {"largo": v["largo"], "ancho": v["ancho"], "alto": v["alto"]},
            "masa_kg": v["masa"], "masa_estimada": v["masa_est"], "velocidad_inicial_kmh": fr[0]["velocidad_kmh"],
            "keyframes": fr})
    cnt = {}
    for s in statics:
        doc["elementos_estaticos"].append(static_json(s, cnt))
    for k, im in enumerate(impacts, 1):
        doc["registro_impactos"].append({
            "id_impacto": f"{im['idp']}_{k:02d}", "tiempo_impacto_s": rnd(im["t"]), "tipo_colision": im["tipo"],
            "punto_contacto": {"x": 0, "y": im["h"], "z": 0},
            "participantes": [{"id": f"vehiculo_{i + 1}", "zona_afectada": z} for i, z in im["part"]]})
    if not doc["elementos_estaticos"]:
        del doc["elementos_estaticos"]
    return doc


# ----------------------------------------------------------------- validador
def validate_choque(doc):
    err = []
    E = err.append
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    for k in ("metadata", "escena", "vehiculos"):
        if k not in doc:
            E(f"falta {k}")
    if err:
        return err
    g = doc["escena"].get("origen_geografico", {})
    if not (num(g.get("latitud")) and -90 <= g["latitud"] <= 90):
        E("latitud invalida")
    if not (num(g.get("longitud")) and -180 <= g["longitud"] <= 180):
        E("longitud invalida")
    imp = doc.get("impacto", {}).get("posicion")
    if imp is not None and imp.get("z", 0) != 0:
        E("impacto.posicion.z debe ser 0")
    ids, hits = set(), []
    for v in doc["vehiculos"]:
        vid = v.get("id", "")
        if not SNAKE.match(vid) or vid in ids:
            E(f"id vehiculo invalido/duplicado {vid}")
        ids.add(vid)
        if v.get("categoria") not in CATALOGO:
            E(f"categoria fuera de catalogo: {v.get('categoria')}")
        d = v.get("dimensiones_m", {})
        if not (num(d.get("largo")) and num(d.get("ancho"))):
            E(f"{vid}: faltan largo/ancho")
        ti = v.get("transform_inicial", {})
        if abs(ti.get("rotacion_grados", {}).get("y", 1e9) - (v.get("rumbo_capturado_grados", 1e9) - 180)) > 0.051:
            E(f"{vid}: rotacion_grados.y != rumbo - 180")
        kf = v.get("keyframes", [])
        if len(kf) < 2:
            E(f"{vid}: menos de 2 keyframes")
            continue
        ts = [k["tiempo_s"] for k in kf]
        if any(b <= a for a, b in zip(ts, ts[1:])):
            E(f"{vid}: keyframes no ordenados")
        a, b = kf[-1], kf[-2]
        if not (a["fase"] == b["fase"] == "detencion_posicion_final" and a["posicion"] == b["posicion"]
                and a["rotacion_grados"] == b["rotacion_grados"]):
            E(f"{vid}: cierre sin 2 keyframes identicos")
        for k in kf:
            if not SNAKE.match(k.get("fase", "x")):
                E(f"{vid}: fase invalida {k.get('fase')}")
            if k["posicion"]["y"] != 0:
                E(f"{vid}: y != 0 en keyframe")
            if any(w in k.get("fase", "") for w in PROHIBIDAS):
                hits.append(k["tiempo_s"])
    ri = doc.get("registro_impactos", [])
    if not hits:
        E("ninguna fase dispara el efecto de impacto")
    elif ri and min(hits) != ri[0]["tiempo_impacto_s"]:
        E(f"fase con palabra prohibida antes del golpe real ({min(hits)} vs {ri[0]['tiempo_impacto_s']})")
    for im in ri:
        for p in im.get("participantes", []):
            if p["id"] not in ids:
                E("participante inexistente")
    seen = set()
    for s in doc.get("elementos_estaticos", []):
        m = re.match(r"^(poste|semaforo|senal|roca|animal|indicio|objeto)_(\d+)$", s.get("id", ""))
        if not m or s["id"] in seen:
            E(f"id estatico invalido/duplicado {s.get('id')}")
            continue
        seen.add(s["id"])
        p, esc = m.group(1), s["transform"].get("escala", {})
        if s.get("tipo") != PREFIJOS[p]:
            E(f"{s['id']}: tipo incorrecto")
        if p in ("poste", "semaforo", "senal") and not (num(esc.get("y")) and esc["y"] > 0):
            E(f"{s['id']}: falta escala.y")
        if p == "indicio" and esc.get("y") != 0.03:
            E(f"{s['id']}: indicio requiere escala.y 0.03")
        if s["transform"]["posicion"]["y"] != 0:
            E(f"{s['id']}: y != 0")
    return err


# ----------------------------------------------------------------- texto de entrada
CM = False  # coma decimal en el texto (el JSON siempre usa punto)


def f(x):
    s = ("%.2f" % x).rstrip("0").rstrip(".")
    s = "0" if s in ("-0", "") else s
    return s.replace(".", ",") if CM else s


def off_txt(e, n, ref="del impacto"):
    p = []
    if abs(e) >= 0.005:
        p.append(f"{f(abs(e))} m al {'Este' if e > 0 else 'Oeste'}")
    if abs(n) >= 0.005:
        p.append(f"{f(abs(n))} m al {'Norte' if n > 0 else 'Sur'}")
    return ("a " + " y ".join(p) + " " + ref) if p else "en el punto de impacto"


def row_text(v_etq, fr, style, last=False, dwell=0):
    e, n = round(fr["e"], 2), round(fr["n"], 2)
    fase = random.choice(FASE_TXT[fr["fase"]])
    est = " (estimado)" if fr["est"] else ""
    h = hnorm(fr["head"])
    t = f(rnd(fr["t"]))
    hs = f(h)
    if style == "ficha":
        if last:
            return f"  - t={t} s | {fase} | {off_txt(e, n)} | rumbo {hs}° | permanece detenido {dwell} s"
        return f"  - t={t} s | {fase} | {off_txt(e, n)} | rumbo {hs}° | {f(rnd(fr['v'], 1))} km/h{est}"
    if last:
        return f"A los {t} s ({fase}) el vehículo {v_etq} queda {off_txt(e, n)}, rumbo {hs}°, y permanece detenido {dwell} s."
    return f"A los {t} s ({fase}), el vehículo {v_etq} está {off_txt(e, n)}, rumbo {hs}°, a {f(rnd(fr['v'], 1))} km/h{est}."


def static_text(s):
    p, d = s["pref"], s["desc"]
    o = off_txt(rnd(s["e"]), rnd(s["n"]))
    if p in ("poste", "semaforo", "senal"):
        return f"{d}, altura {f(s['alt'])} m, ubicado {o}"
    if p == "indicio":
        return f"{d} (marca sobre el piso) de {f(s['w'])} m x {f(s['l'])} m, {o}"
    return f"{d}: {f(s['w'])} m de ancho, {f(s['alt'])} m de alto, {f(s['l'])} m de largo, {o}"


def render_user(scene, vehs, statics, impacts, style):
    g, c = scene["geo"], scene["cond"]
    L = [random.choice(["Convierte estos hechos periciales verificados al JSON de reconstrucción:",
                        "Genera el choque.json a partir de estos datos del perito:",
                        "Hechos verificados del caso. Devuelve únicamente el JSON para Unity:"]), ""]
    L.append(f"Expediente: {scene['exp']}")
    L.append(f"Lugar: {scene['calle']}, {scene['lug'][0]}, {scene['lug'][1]}, México")
    L.append(f"Coordenada de referencia: {g['latitud']}, {g['longitud']} ({'aproximada' if g['estimado'] else 'exacta'}; {g['nota']})")
    if "altura" in g:
        L.append(f"Altitud: {g['altura']} m s. n. m.")
    ox, oy = scene["off"]
    L.append("El punto de impacto coincide con la coordenada." if (ox, oy) == (0.0, 0.0)
             else f"El punto de impacto está {off_txt(ox, oy, 'de la coordenada')}.")
    cs = [f"clima {c['clima']}", f"superficie {c['superficie']}", f"iluminación {c['iluminacion']}",
          f"coeficiente de fricción {f(c['coeficiente_friccion_mu'])}" + (" (estimado)" if c["mu_estimado"] else ""),
          f"sentido de circulación {c['sentido_circulacion']}"]
    if "carriles_por_sentido" in c:
        cs.append(f"{c['carriles_por_sentido']} carril(es) por sentido")
    if "ancho_calle_m" in c:
        cs.append(f"calle de {f(c['ancho_calle_m'])} m, carril de {f(c['ancho_carril_m'])} m")
    if "limite_velocidad_kmh" in c:
        cs.append(f"límite {c['limite_velocidad_kmh']} km/h")
    L.append("Condiciones: " + "; ".join(cs))
    L.append("")
    for v in vehs:
        disp = random.choice(DISP[v["cat"]])
        if "trailer_off" in v:
            L.append(f"Semirremolque acoplado al vehículo A: {disp} {v['modelo']}, {f(v['largo'])} x {f(v['ancho'])} x {f(v['alto'])} m "
                     f"(largo x ancho x alto), {v['masa']} kg{' (estimada)' if v['masa_est'] else ''}. Sigue la misma trayectoria, rumbo, "
                     f"fases y velocidades que el vehículo A, con su centro a {f(v['trailer_off'])} m detrás del centro del tractocamión.")
            continue
        L.append(f"Vehículo {v['etq']}: {disp} {v['modelo']}, {f(v['largo'])} x {f(v['ancho'])} x {f(v['alto'])} m (largo x ancho x alto), "
                 f"{v['masa']} kg{' (estimada)' if v['masa_est'] else ''}.")
        n = len(v["frames"])
        for i, fr in enumerate(v["frames"]):
            L.append(row_text(v["etq"], fr, style, last=(i == n - 1), dwell=v["dwell"]))
    if statics:
        L.append("")
        L.append("Elementos en la escena:")
        L += [f"  - {static_text(s)}" for s in statics]
    L.append("")
    for im in impacts:
        z = "; ".join(f"{vehs[i]['etq']}: zona {zn.replace('_', ' ')}" for i, zn in im["part"])
        L.append(f"Impacto: t={f(im['t'])} s, {im['tipo'].replace('_', ' ')}, altura del contacto {f(im['h'])} m; {z}.")
    return "\n".join(L)


# ----------------------------------------------------------------- ejemplo completo
def make_example():
    global CM
    CM = random.random() < 0.4
    r = random.random()
    if r < 0.20:
        vehs, st, im, h = sc_alcance()
    elif r < 0.30:
        vehs, st, im, h = sc_alcance(tracto=True)
    elif r < 0.45:
        vehs, st, im, h = sc_reversa()
    elif r < 0.65:
        vehs, st, im, h = sc_cruce()
    elif r < 0.77:
        vehs, st, im, h = sc_fijo("poste")
    elif r < 0.89:
        vehs, st, im, h = sc_fijo("animal")
    else:
        vehs, st, im, h = sc_fijo("bache")
    background(st)
    scene = make_scene(h)
    doc = build_json(scene, vehs, st, im)
    errs = validate_choque(doc)
    if errs:
        raise ValueError(f"ejemplo invalido: {errs}")
    out = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    assert json.loads(out) == doc
    user = render_user(scene, vehs, st, im, random.choice(["ficha", "relato"]))
    return {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": out}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--val", type=float, default=0.05)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    random.seed(a.seed)
    rows = [make_example() for _ in range(a.n)]
    k = max(1, int(a.n * a.val))
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for name, part in (("train", rows[k:]), ("val", rows[:k])):
        with open(Path(a.out) / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for r in part:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tok = [sum(len(m["content"]) for m in r["messages"]) / 3.0 for r in rows]
    print(f"OK: {len(rows) - k} train / {k} val -> {a.out}/")
    print(f"tokens aprox por ejemplo: media {sum(tok)/len(tok):.0f}, max {max(tok):.0f}  (limite 4096)")
    if max(tok) > 3800:
        print("AVISO: hay ejemplos cerca del limite; revisa con el tokenizer real antes de entrenar.")


if __name__ == "__main__":
    main()
