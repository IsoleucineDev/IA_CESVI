# Modelo CESVI (chatbot de entrevista pericial)

Qwen2.5-7B ajustado que entrevista al perito **un tema a la vez**. El código del proyecto lleva el checklist y el
porcentaje; el modelo solo redacta la pregunta y extrae el valor de cada respuesta.

| Archivo | Para qué sirve |
|---|---|
| `schema.py` | Fuente de verdad de prompts, catálogo de temas y parsers (usado en entrenamiento) |
| `chat_cli.py` | Chat de prueba en terminal con MLX |
| `Modelfile` | Receta de Ollama para cargar el `.gguf` |
| `mock-model.mjs` | Modelo FALSO compatible con Ollama, solo para probar el cableado sin pesos |

> `api/_cesvi-model.ts` es el port a TypeScript de `schema.py`. **Si cambian prompts o temas en `schema.py`,
> hay que cambiarlos también ahí**, o el modelo verá en producción algo distinto a lo que vio en entrenamiento.

Los pesos (`*.gguf`, adaptadores) NO están en git. Pídeselos a quien entrenó el modelo.

## Flujo
`Front (App.tsx)` → `POST /api/ai/chat` (`api/[...path].ts`) → `api/_cesvi-model.ts` → servidor del modelo (Ollama o mlx_lm.server).
La sesión de la entrevista (tipo de choque, datos, pregunta pendiente) viaja en cada petición, así que funciona también en Vercel.
