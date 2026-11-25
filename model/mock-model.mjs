// Servidor FALSO compatible con Ollama, solo para probar el cableado (front -> /api -> modelo)
// sin necesitar los pesos del modelo real. NO es el modelo: sus preguntas son plantillas.
//   node model/mock-model.mjs        (escucha en http://localhost:11434)
import http from "node:http";

const PORT = Number(process.env.MOCK_PORT || 11434);
const NUMERIC = /(^velocidad_.*_kmh$)|(_cm$)|(^huellas_frenado_m$)/;

function answerQ(user) {
  const first = /^- (\S+): (.+)$/m.exec(user);
  if (!first) return "TEMA: FIN";
  return `TEMA: ${first[1]}\nPREGUNTA: [mock] ${first[2]}. ¿Qué puede indicar al respecto?`;
}

function answerE(user) {
  const tema = /^TEMA: (\S+)/m.exec(user)?.[1] ?? "desconocido";
  const resp = /^RESPUESTA DEL PERITO: (.*)$/m.exec(user)?.[1] ?? "";
  if (/^\s*saltar/i.test(resp)) return JSON.stringify({ [tema]: "__saltado__" });
  if (NUMERIC.test(tema)) {
    const n = /-?\d+(?:[.,]\d+)?/.exec(resp);
    return JSON.stringify({ [tema]: n ? Number(n[0].replace(",", ".")) : null });
  }
  return JSON.stringify({ [tema]: resp.trim() });
}

http
  .createServer((req, res) => {
    const send = (code, obj) => {
      res.writeHead(code, { "Content-Type": "application/json" });
      res.end(JSON.stringify(obj));
    };
    if (req.method === "GET" && req.url === "/api/tags") return send(200, { models: [{ name: "cesvi:latest" }] });
    if (req.method === "POST" && req.url === "/api/chat") {
      let raw = "";
      req.on("data", (c) => (raw += c));
      req.on("end", () => {
        const { messages = [] } = JSON.parse(raw || "{}");
        const system = messages.find((m) => m.role === "system")?.content ?? "";
        const user = messages.find((m) => m.role === "user")?.content ?? "";
        const content = system.startsWith("Extraes datos") ? answerE(user) : answerQ(user);
        console.log(`[mock] ${system.startsWith("Extraes") ? "EXTRAER" : "PREGUNTAR"} -> ${content.replace(/\n/g, " | ")}`);
        send(200, { message: { role: "assistant", content } });
      });
      return;
    }
    send(404, { error: "no encontrado" });
  })
  .listen(PORT, () => console.log(`Mock del modelo CESVI en http://localhost:${PORT}`));
