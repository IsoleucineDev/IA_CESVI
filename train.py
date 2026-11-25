#!/usr/bin/env python3
"""
QLoRA con Unsloth: hechos periciales -> choque.json (Unity).
Uso básico:   python train.py
Si hay OOM:   python train.py --seq 3072        (o --model unsloth/Qwen2.5-3B-Instruct-bnb-4bit)
Prueba corta: python train.py --max_steps 20 --no_merge
"""
import argparse, inspect, json, os, platform
from pathlib import Path
from unsloth import FastLanguageModel, is_bfloat16_supported   # unsloth SIEMPRE antes de trl/transformers
from unsloth.chat_templates import train_on_responses_only
import torch
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
from gen_dataset import validate_choque

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit")
ap.add_argument("--data", default="data")
ap.add_argument("--out", default="outputs")
ap.add_argument("--seq", type=int, default=4096)
ap.add_argument("--epochs", type=float, default=2)
ap.add_argument("--max_steps", type=int, default=-1)
ap.add_argument("--bs", type=int, default=1)
ap.add_argument("--ga", type=int, default=8)
ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--alpha", type=int, default=32)
ap.add_argument("--smoke", type=int, default=5, help="ejemplos de val para probar JSON al terminar")
ap.add_argument("--no_merge", action="store_true")
a = ap.parse_args()

data_dir = Path(a.data)
out_dir = Path(a.out)
train_file = data_dir / "train.jsonl"
val_file = data_dir / "val.jsonl"
ckpt_dir = out_dir / "ckpt"
lora_dir = out_dir / "lora"
merged_dir = out_dir / "merged_16bit"

# 1) Modelo base 4-bit + LoRA
model, tok = FastLanguageModel.from_pretrained(a.model, max_seq_length=a.seq, dtype=None, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(
    model, r=a.rank, lora_alpha=a.alpha, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth", random_state=3407)

# 2) Dataset -> texto con la plantilla de chat del modelo; descarta lo que exceda seq
ds = load_dataset("json", data_files={"train": str(train_file), "val": str(val_file)})
ds = ds.map(lambda ex: {"text": tok.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=False)})
ntok = lambda t: len(tok(t, add_special_tokens=False).input_ids)
lens = [ntok(t) for t in ds["train"]["text"]]
print(f"TOKENS por ejemplo: media {sum(lens)/len(lens):.0f} | max {max(lens)} | limite {a.seq}")
before = len(ds["train"])
ds = ds.filter(lambda ex: ntok(ex["text"]) <= a.seq)
print(f"Ejemplos train: {before} -> {len(ds['train'])} (descartados por longitud: {before - len(ds['train'])})")
raw_val = [json.loads(l) for l in open(val_file, encoding="utf-8")]
ds = ds.remove_columns(["messages"])

# 3) Trainer (compatible con versiones nuevas y viejas de trl)
cfg_kw = dict(
    output_dir=str(ckpt_dir), per_device_train_batch_size=a.bs, per_device_eval_batch_size=1,
    gradient_accumulation_steps=a.ga, num_train_epochs=a.epochs, max_steps=a.max_steps,
    learning_rate=a.lr, lr_scheduler_type="cosine", warmup_ratio=0.05, weight_decay=0.01,
    optim="adamw_8bit", bf16=is_bfloat16_supported(), fp16=not is_bfloat16_supported(),
    logging_steps=5, eval_strategy="steps", eval_steps=100, save_strategy="steps", save_steps=100,
    save_total_limit=2, seed=3407, report_to="none", dataset_text_field="text", packing=False)
fields = SFTConfig.__dataclass_fields__
cfg_kw["max_length" if "max_length" in fields and "max_seq_length" not in fields else "max_seq_length"] = a.seq
if platform.system() == "Windows" and "dataset_num_proc" in fields:
    cfg_kw["dataset_num_proc"] = 1
tr_kw = dict(model=model, train_dataset=ds["train"], eval_dataset=ds["val"], args=SFTConfig(**cfg_kw))
tr_kw["processing_class" if "processing_class" in inspect.signature(SFTTrainer.__init__).parameters else "tokenizer"] = tok
trainer = SFTTrainer(**tr_kw)
# Solo se calcula pérdida sobre la respuesta del asistente (el JSON), no sobre system/user
trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\n", response_part="<|im_start|>assistant\n")

print(f"VRAM antes de entrenar: {torch.cuda.max_memory_reserved()/1e9:.1f} GB")
trainer.train()
print(f"VRAM pico: {torch.cuda.max_memory_reserved()/1e9:.1f} GB")

# 4) Guardar adaptador LoRA (pequeño; respaldo para re-fusionar después)
model.save_pretrained(str(lora_dir)); tok.save_pretrained(str(lora_dir))
print("Adaptador guardado en", str(lora_dir))

# 5) Prueba rápida: ¿el modelo emite JSON limpio y válido?
if a.smoke:
    FastLanguageModel.for_inference(model)
    ok = 0
    for i, ex in enumerate(raw_val[:a.smoke]):
        msgs = ex["messages"][:2]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
        out = model.generate(input_ids=ids, max_new_tokens=3600, do_sample=False, use_cache=True)
        txt = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        try:
            errs = validate_choque(json.loads(txt))
        except Exception as e:
            errs = [f"json.loads fallo: {e}"]
        ok += not errs
        print(f"[smoke {i+1}/{a.smoke}]", "OK" if not errs else f"FALLA {errs[:3]}")
    print(f"SMOKE: {ok}/{a.smoke} válidos")

# 6) Fusionar LoRA + base a 16-bit (entrada para GGUF)
if not a.no_merge:
    model.save_pretrained_merged(str(merged_dir), tok, save_method="merged_16bit")
    print("Modelo fusionado en", str(merged_dir))
