# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ScamantiQ is a Gradio app that explains *how* a message tries to manipulate the reader. It labels a message with tactics from a fixed five-label taxonomy (`urgency`, `impersonation`, `isolation`, `reward`, `threat`), quotes verbatim evidence for each, and explains it. It is explicitly **not a scam detector** and must never say "this is a scam"; keep that framing in prompts, UI text and docs. No model is trained; the LLM is a pluggable configuration choice.

## Commands

Work inside the `scamantiq` conda environment (`conda activate scamantiq`, or `pip install -r requirements.txt`).

```bash
python -m pytest -q                                   # full suite, 49 tests, offline, ~5 s
python -m pytest tests/test_validator.py -q           # one file
python -m pytest tests/test_analyzer.py::test_analyze_retries_on_bad_evidence -q   # one test

python app.py                                         # UI at http://127.0.0.1:7860 (default provider: local Ollama gemma4:12b)
SCAMANTIQ_PROVIDER=mock python scripts/ui_preview.py 0 7862   # UI with example 0 pre-rendered, no backend needed

python evaluate.py                                    # 150-message benchmark on the current provider
python evaluate.py --provider sglang --no-cache --out results/eval_x.json
python evaluate.py --category hard_benign --limit 5

python scripts/build_demo_cache.py --all              # regenerate data/demo_cache.json (needs a live backend)
```

There is no linter or formatter configured. Tests never touch the network: they use `MockProvider`, a fake in-process HTTP server (`tests/test_openai_compat.py`), or the `settings` fixture in `tests/conftest.py` (mock provider, cache disabled, tmp cache path).

## Architecture

The whole pipeline is one LLM call plus code-level verification. Read `scamantiq/analyzer.py` first; it is the spine.

```
app.py / evaluate.py
   └─ Analyzer.analyze(message)                  scamantiq/analyzer.py
        ├─ DemoCache.get  (if enabled)           scamantiq/cache.py
        ├─ provider.complete_json(system, user, LLM_JSON_SCHEMA)   scamantiq/providers/*
        ├─ parse_llm_output -> LLMAnalysis       scamantiq/schema.py  (drops unknown labels, coerces types)
        ├─ validate(analysis, message)           scamantiq/validator.py
        │     rejected quotes -> retry_prompt, up to settings.max_retries (default 1)
        └─ AnalysisResult (verified tactics + char spans)
```

Key invariants that several files rely on:

- **Evidence is verified by code, not trusted from the model.** `validator.locate` tolerates case, whitespace and curly-quote differences when *finding* a quote, but the span text returned is always the exact source substring. A tactic with no surviving quote is dropped, and a message with no verified evidence is never marked suspicious (enforced in `Analyzer._run`). Don't weaken this.
- **The taxonomy is the single source of truth.** `scamantiq/taxonomy.py` defines labels, definitions, examples, colours and advice. `prompt.py` injects it into the system prompt, `schema.py` derives the `Label` literal and `normalise_label` from it, `app.py` uses its colours, and `evaluation.py` validates gold labels against it. Changing a label means touching the test set and the demo cache too.
- **Providers share one interface.** `LLMProvider.complete_json(system, user, schema) -> raw text` and `healthcheck() -> (ok, status)` in `providers/base.py`. `build_provider` in `providers/__init__.py` dispatches on `Settings.provider`. Presets (`sglang`, `vllm`, `groq`, `openrouter`, `deepseek`, `openai`) all map to the `openai` provider type with different `base_url`; `ollama`, `anthropic`, `gemini`, `mock` have their own adapters. `OpenAICompatProvider` auto-detects the served model via `GET /v1/models` when `SCAMANTIQ_MODEL` is empty, and degrades structured output `json_schema -> json_object -> none`, remembering what worked.
- **Config comes from env only.** `scamantiq/config.py` loads `.env` via python-dotenv and builds a `Settings` dataclass from `PRESETS` plus `SCAMANTIQ_*` overrides. Adding a backend usually means adding a preset entry and, if the protocol is new, a provider class and a `build_provider` branch.
- **Offline fallback.** `data/demo_cache.json` is keyed by whitespace-normalised message text and holds results for every UI example and every test-set message. `Analyzer` serves it before calling the model (when `SCAMANTIQ_USE_CACHE` is on) and again if the provider raises `ProviderError`. The `mock` provider has no answers of its own, so `mock` mode effectively means "cache only". After changing the prompt, taxonomy or default model, rebuild the cache or the demo will show stale results.

## Data and evaluation

- `data/test_set.jsonl`: 150 annotated messages (30 per category), categories `familiar`, `paraphrased`, `subtle_scam`, `benign`, `hard_benign`. Each has `labels` and per-label `evidence` spans. `check_dataset` (run by `evaluate.py` and by `tests/test_evaluation.py`) requires unique ids, known labels, and every gold span to be a verbatim substring of its message. Three `subtle_scam` items (`ss01`, `ss14`, `ss29`) are intentionally labelled empty.
- `scamantiq/evaluation.py` computes detection accuracy/F1/FPR, macro/micro/per-label F1, grounding rate (on the model's *raw* quotes, before validation), token-level span F1, and mean attempts. `results/` holds committed reports for gemma4:12b (Ollama) and Qwen2.5-7B (SGLang); the README tables are derived from them, so update both together.

## UI notes

`app.py` holds `EXAMPLES` and `EXAMPLE_LABELS` (must stay the same length and unique; tested), the rendering helpers (`render_*`, which must HTML-escape all model output; tested), the CSS string, and `build_app(initial_message)`. The analyse button is exposed as the Gradio API endpoint `/analyse`. `scripts/ui_preview.py` imports `build_app`, `CSS` and `EXAMPLES` from `app.py` for screenshot work.

## Gitignored items worth knowing

`.env`, `.gradio/`, `flagged/` and the `.docx` plan at the repo root are ignored. `docs/` is in `.gitignore` but the two README screenshots under `docs/screenshots/` were committed before that rule and remain tracked; `docs/proposal/` is not. Keys go in `.env` (see `.env.example`); only the provider in use needs one, and `SCAMANTIQ_API_KEY` overrides the per-provider variable.
