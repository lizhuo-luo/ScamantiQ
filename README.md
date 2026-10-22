# ScamantiQ

**Explainable analysis of how a message tries to manipulate you.**
Paste a suspicious text and ScamantiQ names the manipulation tactics it uses, quotes the exact phrases as evidence, and explains each one in plain language.

> ScamantiQ is an educational aid, **not a scam detector**. It never says "this is a scam". A message can use pressure tactics and still be legitimate, and a scam can be written without any of them. The user makes the call; ScamantiQ shows them what to look at.

![ScamantiQ analysing a fake bank alert](docs/screenshots/result-light.png)

<details>
<summary>Dark theme</summary>

![ScamantiQ in dark mode](docs/screenshots/result-dark.png)
</details>

## Contents

1. [What it does](#what-it-does)
2. [Quick start](#quick-start)
3. [How it works](#how-it-works)
4. [The five tactics](#the-five-tactics)
5. [Choosing an LLM backend](#choosing-an-llm-backend)
6. [Evaluation](#evaluation)
7. [Limitations](#limitations)
8. [Project layout](#project-layout)
9. [Development](#development)

## What it does

| | |
|---|---|
| **Detects** | whether a message contains persuasive or coercive patterns |
| **Identifies** | one or more tactics from a fixed taxonomy of five |
| **Grounds** | every tactic in a verbatim quote from the message, checked by code, not by the model |
| **Explains** | each tactic for a non-expert, with practical advice on what to do next |

The LLM is pluggable: a local Ollama, SGLang or vLLM server (free, nothing leaves the machine) or a cloud API (Groq, Gemini, OpenRouter, DeepSeek, OpenAI, Anthropic). Every backend is asked for schema-constrained JSON so labels and fields stay well-formed, and the same validator checks every quote whichever model produced it.

What it does **not** do: decide whether a message is fraudulent, check who sent it, follow links, or replace advice from your bank or the police.

## Quick start

```bash
conda activate scamantiq          # or: pip install -r requirements.txt
python app.py                      # open http://127.0.0.1:7860
```

The default backend is a local Ollama server running `gemma4:12b`. Any other backend is one environment variable away, or a line in `.env` (see `.env.example`):

```bash
SCAMANTIQ_PROVIDER=sglang python app.py                 # local SGLang server on :30000
SCAMANTIQ_PROVIDER=groq GROQ_API_KEY=... python app.py  # cloud API
```

`SCAMANTIQ_SHARE=1` adds a temporary public `gradio.live` link. If the backend is unreachable, the app serves precomputed answers for the built-in examples and the test set, so the demo still works offline.

## How it works

![Every highlighted phrase is checked against the message before it is shown](docs/screenshots/workflow.jpg)

1. **Detect and identify.** One LLM request judges whether manipulation is present and labels the tactics from the fixed list. Detection, classification, evidence and explanation come from a single call to keep latency and cost low.
2. **Ground.** For each tactic the model must quote the exact words that support it.
3. **Verify.** Python checks that every quote is a verbatim substring of the message. Quotes that are not are rejected and the model is asked once to correct them. A tactic with no surviving evidence is dropped, and a message with no verified evidence is never flagged. Case, whitespace and curly-quote differences are tolerated when *locating* a quote, but the text shown to the user is always the exact source span.
4. **Explain.** Each verified tactic is shown with its evidence, a plain-language explanation and the model's self-reported confidence, bucketed as high, medium or low.

No model is trained and no GPU is required; the LLM is a configuration choice.

## The five tactics

![The five tactics, each named only when it can be quoted from the message](docs/screenshots/tactics.png)

| Label | Tactic | What it looks like | Why it is in the taxonomy |
|---|---|---|---|
| `urgency` | Urgency | deadlines, countdowns, "act now" | Time pressure stops the reader from verifying. The "pressure you to act immediately" warning sign; scarcity in Cialdini; the *time* principle in Stajano and Wilson. |
| `impersonation` | Impersonation / authority | "This is your bank", "Hi Mum, new number" | Borrowing a trusted identity is the entry point of most phishing and family-emergency scams. The "pretend to be an organisation you know" sign; the *authority* principle. |
| `isolation` | Isolation / secrecy | "don't tell the bank", "keep this between us" | Cutting the target off from second opinions is what makes the other tactics hard to break; characteristic of romance, courier and safe-account scams. |
| `reward` | Reward / incentive | prizes, refunds, jobs, guaranteed returns | Exploits *need and greed*; the "there's a prize" half of the "problem or prize" sign. |
| `threat` | Threat / penalty | arrest, fines, account closure, exposure | Exploits fear; the "there's a problem" half of "problem or prize" and the coercive counterpart of reward. |

**Why five, and why these?** The taxonomy is small and fixed so that outputs are comparable across messages and models, and so that each label has an operational definition a non-expert can check against the quoted evidence. The five labels cover the warning signs published by consumer-protection agencies such as the US FTC (impersonation, problem or prize, pressure to act, unusual payment). Reward and threat are kept apart because they need different explanations; isolation is added because it is the tactic that most directly removes the user's ability to seek help. The "unusual payment method" sign is about the requested action rather than the wording, so it is handled by the safety disclaimer instead of a label.

Two boundary rules in the prompt keep legitimate messages unflagged: an organisation naming itself is only impersonation when the borrowed identity is used to ask for a payment, details, a code, a call or a visit to an unofficial link; and a genuine "do not share this code with anyone" warning is security advice, not isolation. See [What the prompt rules changed](#what-the-prompt-rules-changed) for their measured effect.

Definitions, examples, colours and advice text live in `scamantiq/taxonomy.py`; the rules live in `scamantiq/prompt.py`. Both are injected into the system prompt.

References: Cialdini, *Influence: The Psychology of Persuasion* (1984) · Stajano and Wilson, "Understanding scam victims: seven principles for systems security", *Communications of the ACM* 54(3), 2011 · US Federal Trade Commission, "How to avoid a scam".

## Choosing an LLM backend

All backends implement the same two-method interface (`complete_json`, `healthcheck`) in `scamantiq/providers/`. Select one with `SCAMANTIQ_PROVIDER`:

| Value | Backend | Key | Default model / notes |
|---|---|---|---|
| `ollama` (default) | local Ollama `/api/chat` | none | `gemma4:12b`; GGUF models, schema-constrained output |
| `sglang` | local SGLang server, OpenAI-compatible | none | model read from the server; HF weights, high throughput |
| `vllm` | local vLLM server, OpenAI-compatible | none | model read from the server; HF weights, high throughput |
| `groq` | Groq (OpenAI-compatible) | `GROQ_API_KEY` | `llama-3.3-70b-versatile`; free tier, very fast |
| `gemini` | Google Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash`; free tier, schema-constrained |
| `openrouter` | OpenRouter (OpenAI-compatible) | `OPENROUTER_API_KEY` | `llama-3.3-70b-instruct:free` |
| `deepseek` | DeepSeek (OpenAI-compatible) | `DEEPSEEK_API_KEY` | `deepseek-flash` (V4.1-Flash, thinking on by default); very low cost |
| `openai` | OpenAI chat completions | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `anthropic` | Anthropic Messages API | `ANTHROPIC_API_KEY` | `claude-haiku-5-5`; schema-constrained; `claude-sonnet-5-5` / `claude-opus-5-5` via `SCAMANTIQ_MODEL` |
| `mock` | cached demo answers only | none | offline tests and demos |

`SCAMANTIQ_MODEL` and `SCAMANTIQ_BASE_URL` override the preset, and `SCAMANTIQ_API_KEY` overrides every per-provider key. Any OpenAI-compatible endpoint works through the `openai` preset, for example:

```ini
SCAMANTIQ_PROVIDER=openai
SCAMANTIQ_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SCAMANTIQ_MODEL=qwen-plus
SCAMANTIQ_API_KEY=sk-...
```

The OpenAI-compatible provider asks `GET /v1/models` for the served model when `SCAMANTIQ_MODEL` is empty, and requests structured output in the strongest form the server accepts (`json_schema`, then `json_object`, then none), remembering what worked. Other knobs: `SCAMANTIQ_MAX_RETRIES` (default 1), `SCAMANTIQ_TEMPERATURE` (default 0; ignored by models that think), `SCAMANTIQ_EFFORT` (reasoning effort `low`/`medium`/`high`/`max` for DeepSeek V4 and Claude 5.5, default: the provider's own), `SCAMANTIQ_TIMEOUT` (default 120 s), `SCAMANTIQ_USE_CACHE` (default on), `SCAMANTIQ_HOST`, `SCAMANTIQ_PORT`. Cloud adapters retry HTTP 429 and 5xx responses up to four times with backoff.

**Ollama vs SGLang/vLLM.** Ollama runs quantised GGUF models and is the easiest to set up. SGLang and vLLM serve original HuggingFace weights with continuous batching, which is better for GPU machines and for running the evaluation quickly. All three support schema-constrained JSON.

<details>
<summary>Running SGLang or vLLM</summary>

```bash
conda create -n sglang python=3.12 && conda activate sglang
pip install "sglang[all]"
python -m sglang.launch_server --model-path <hf-model> --port 30000
# then, in the scamantiq env:
SCAMANTIQ_PROVIDER=sglang python app.py
```

SGLang compiles some kernels at start-up and needs a CUDA toolkit of 12.9 or newer on `PATH`. If the system `nvcc` is older (symptoms: `NVCC version must be at least 12.9` or `Value 'c++20' is not defined for option 'std'`), install one into the SGLang environment and disable the FP8 DeepGEMM path, which bf16 models do not use anyway:

```bash
conda install -c nvidia "cuda-nvcc=13.0" "cuda-cudart-dev=13.0" "cuda-crt-dev_linux-64=13.0"
export CUDA_HOME=$CONDA_PREFIX PATH=$CONDA_PREFIX/bin:$PATH
SGLANG_ENABLE_JIT_DEEPGEMM=false python -m sglang.launch_server --model-path <hf-model> --port 30000
```

vLLM is the same with `python -m vllm.entrypoints.openai.api_server --model <hf-model> --port 8000` and `SCAMANTIQ_PROVIDER=vllm`.
</details>

**Offline cache.** `data/demo_cache.json` holds precomputed results for every built-in example and every test-set message. It is served when the backend is down and is all the `mock` provider has. Rebuild it after changing the prompt, the taxonomy or the default model:

```bash
python scripts/build_demo_cache.py --all --force
```

## Evaluation

### Test set

`data/test_set.jsonl` contains 150 messages, 30 per category, each annotated with gold tactic labels and gold evidence spans. The first 90 were written by the project team; the remaining 60 were drafted with an LLM assistant to balance the categories and then reviewed and annotated by hand.

| Category | n | Purpose |
|---|---|---|
| `familiar` | 30 | Classic scam templates: bank lock-out, prize, tax warrant, parcel fee, courier redelivery, utility disconnection… |
| `paraphrased` | 30 | Scams with unseen wording and different scenarios, to measure generalisation |
| `subtle_scam` | 30 | Low-cue scams: wrong-number openers, slow-burn investment and romance grooming, politely worded advance-fee offers, task and pet scams, invoice redirection. Three (`ss01`, `ss14`, `ss29`) contain no taxonomy tactic in the text and are labelled empty on purpose. |
| `benign` | 30 | Ordinary personal, commercial and institutional messages |
| `hard_benign` | 30 | Legitimate messages that *look* like scams: real fraud alerts, OTP warnings, payment reminders with deadlines, genuine refunds and jury summons, a real "lost my phone" text |

The loader rejects the file if an id repeats, a label is unknown, or a gold span is not a verbatim substring of its message.

### Metrics

Reported overall and per category by `evaluate.py`:

| Metric | Measures |
|---|---|
| Detection accuracy / F1, false-positive rate | whether the message is flagged at all |
| Macro F1, micro F1, per-label F1 | multi-label tactic classification over the five labels |
| Grounding rate | share of the model's *raw* quotes that occur exactly in the source, counted before the validator repairs or rejects anything |
| Span F1 | token-level overlap between predicted and gold evidence spans, per label |
| Mean attempts | how often the retry was needed |

```bash
python evaluate.py --no-cache                             # current provider, every answer from the model
python evaluate.py --provider groq --out results/groq.json
python evaluate.py --category hard_benign --limit 5       # one subset
```

### Results

Four models, all with `--no-cache` and the current prompt: two local models served by Ollama on one H200, and two cloud APIs run with their default thinking settings (DeepSeek V4.1-Flash thinks at `high` effort unless told otherwise; Claude Opus 5.5 uses adaptive thinking at `medium`). Per-message times are wall-clock: a shared GPU for the local models, network plus thinking time for the APIs. They vary between runs.

| Model | Detection acc. | FPR on hard_benign | Macro F1 | Micro F1 | Grounding | Span F1 | Time per message |
|---|---|---|---|---|---|---|---|
| gemma4:12b (Ollama) | 0.967 | 0.033 | 0.919 | 0.916 | 1.000 | 0.744 | 1.5 s |
| qwen3.8:27b-q4_K_M (Ollama) | 0.960 | 0.000 | 0.894 | 0.890 | 1.000 | 0.725 | 2.7 s |
| deepseek-flash (DeepSeek V4.1-Flash-1017) | 0.980 | 0.033 | 0.916 | 0.914 | 1.000 | 0.712 | 3.6 s |
| claude-opus-5-5 (Anthropic) | 0.987 | 0.000 | 0.905 | 0.901 | 1.000 | 0.678 | 4.8 s |

Per-label F1 and exact label-set matches:

| | gemma4:12b | qwen3.8:27b | deepseek-flash | claude-opus-5-5 |
|---|---|---|---|---|
| urgency | 0.929 | 0.885 | 0.939 | 0.911 |
| impersonation | 0.887 | 0.875 | 0.891 | 0.860 |
| isolation | 0.944 | 0.947 | 0.944 | 0.900 |
| reward | 0.941 | 0.923 | 0.928 | 0.957 |
| threat | 0.894 | 0.840 | 0.877 | 0.897 |
| exact label-set matches (of 150) | 130 | 115 | 126 | 120 |

By category, detection accuracy with micro F1 after the slash for the scam categories:

| Category | gemma4:12b | qwen3.8:27b | deepseek-flash | claude-opus-5-5 |
|---|---|---|---|---|
| familiar | 1.000 / 0.962 | 1.000 / 0.947 | 1.000 / 0.962 | 1.000 / 0.951 |
| paraphrased | 1.000 / 0.943 | 1.000 / 0.945 | 1.000 / 0.917 | 1.000 / 0.899 |
| subtle_scam | 0.867 / 0.788 | 0.800 / 0.676 | 0.933 / 0.812 | 0.933 / 0.800 |
| benign | 1.000 | 1.000 | 1.000 | 1.000 |
| hard_benign | 0.967 | 1.000 | 0.967 | 1.000 |

`qwen3.8:latest` is the same 27B Q4_K_M weights under another tag and scored within 0.003 of the run above.

### What the prompt rules changed

The first run on the expanded set flagged two genuine `hard_benign` messages: a Chase card-decline text and a Microsoft sign-in code, both with the brand name itself quoted as impersonation evidence; the Qwen model also read a genuine OTP warning ("Do not share this code with anyone, including bank staff") as isolation. Two rules were added to the system prompt in response, and gemma4 was re-run on the full set:

| gemma4:12b | Before the rules | After |
|---|---|---|
| False positives on hard_benign | 2 of 30 | 1 of 30 |
| Exact label-set matches | 124 of 150 | 130 of 150 |
| Impersonation F1 | 0.876 | 0.887 |
| Isolation F1 | 0.919 | 0.944 |
| Macro F1 | 0.914 | 0.919 |
| Span F1 | 0.758 | 0.744 |

Both models gained from the rules. gemma4's one remaining false positive is the Chase decline text, which it still reads as impersonation plus urgency because of the "reply NO and we'll cancel your card" line. An earlier wording that called card-freezing a protective step removed that too, but cost threat recall on two real scams, so it was dropped. Span F1 slipped slightly because the rule's examples ("Netflix:") nudge the model toward quoting just the name rather than the whole claim. For qwen3.8:27b the rules removed both of its false positives (the Chase decline and the OTP warning), lifted macro F1 from 0.847 to 0.894 and isolation F1 from 0.850 to 0.947, and raised exact label-set matches from 106 to 115. The rules were tuned on these failures, so see the caveat under Limitations.

### Reading the numbers

Every quote all four models produced was verbatim and no retry was needed, so the validator had nothing to repair in these runs; its value shows on weaker models and in earlier runs, where paraphrased quotes were caught and corrected. No model flagged any of the 30 `benign` messages. On `hard_benign`, Opus 5.5 and Qwen are clean, gemma4 still flags the Chase decline text, and DeepSeek flags the genuine "lost my phone, texting from Jess's" message as impersonation, which is a defensible reading of a text that matches the "Hi Mum" pattern.

Detection and labelling pull apart. Claude Opus 5.5 has the best detection numbers (no scam missed, nothing benign flagged) but a lower macro F1 than gemma4 and DeepSeek and the lowest span F1: it labels `impersonation` on seven `subtle_scam` messages whose gold labels do not include it, and it quotes almost two passages per message, longer than the annotators' spans. gemma4:12b, the smallest model, still has the highest macro F1 and the most exact label-set matches, with DeepSeek V4.1-Flash close behind on labels and slightly ahead on detection. A larger or more expensive model is therefore not automatically better for this task; the prompt and the validator do much of the work.

`subtle_scam` remains the hardest category. The three deliberately empty-labelled messages are read differently by each model: gemma4 flags all three, Qwen and Opus two, DeepSeek only the overseas tenant who offers to pay a deposit sight unseen. Outright misses are rare: Opus misses none, gemma4 and DeepSeek one each (the parking-fine notice and the soft investment recommendation), Qwen four. Several of these readings are defensible, which is the kind of annotation disagreement a small benchmark cannot settle. Per-message predictions are in `results/`.

## Limitations

- **Small prototype benchmark.** 150 messages are enough to compare configurations and catch regressions, not to make claims about real-world performance. Messages are English and short; most are UK/US/AU-centric with a few from Canada, Singapore, India and New Zealand. 60 of them were drafted with an LLM assistant, which may favour phrasing that language models find easy. There is no inter-annotator agreement study; gold labels reflect the team's reading.
- **The prompt rules were written after looking at this benchmark's failures**, so the `hard_benign` numbers after the rules are optimistic. A fresh set of legitimate alerts is the only honest test of them.
- **The taxonomy is not exhaustive.** Flattery, reciprocity, social proof and deception without pressure have no label. Some scams, such as the wrong-number opener, contain no tactic in the message text and will correctly produce "no strong tactic detected" even though the follow-up conversation would be a scam.
- **Tactics are not verdicts.** Legitimate fraud alerts, OTP messages and payment reminders share wording with scams. ScamantiQ only sees wording; it knows nothing about the sender, the link destination or the recipient's real account.
- **LLM dependence.** Labels, explanations and confidence scores come from a general-purpose model and vary between models and runs. The validator guarantees that quoted evidence is real; it does not guarantee that the label or explanation is right.
- **Confidence is self-reported** by the model and not a calibrated probability; the UI shows it as high, medium or low for that reason.
- **Text only.** No image or OCR input in this version.

## Project layout

```
app.py                       Gradio interface
evaluate.py                  evaluation CLI
scamantiq/
  taxonomy.py                the five tactics: definitions, examples, colours, advice
  prompt.py                  system prompt with the boundary rules, user and retry prompts
  schema.py                  Pydantic models and the JSON schema sent to the model
  validator.py               exact-substring evidence check
  analyzer.py                call → parse → validate → retry → result
  providers/                 ollama, openai-compatible (sglang, vllm, cloud APIs), anthropic, gemini, mock
  config.py                  settings and provider presets
  cache.py                   offline demo cache
  evaluation.py              metrics (scikit-learn)
data/test_set.jsonl          150 annotated messages, 30 per category
data/demo_cache.json         cached results for every example and test-set message
results/                     evaluation reports (one .txt and one .json per model)
docs/screenshots/            README images
scripts/build_demo_cache.py  precompute results for the cache
scripts/ui_preview.py        launch the UI with a pre-rendered example
tests/                       pytest suite, no network required
```

## Development

```bash
python -m pytest -q                                             # 63 tests, offline, about 10 s
SCAMANTIQ_PROVIDER=mock python scripts/ui_preview.py 0 7862    # UI with example 0 pre-rendered, for styling and screenshots
```

The Gradio app also exposes its analysis as an API endpoint (`/analyse`), callable with `gradio_client`: input one message string, output the rendered HTML and the full result JSON.
