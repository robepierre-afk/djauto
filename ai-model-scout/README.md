# AI Model Scout

A weekly scan of the internet for AI models with **free, downloadable weights** you can run
on your own media machine. It covers two areas:

1. **Open LLMs** that compete with paid models like Claude and ChatGPT (Qwen, DeepSeek, Llama,
   Mistral, Gemma, GLM, Kimi, gpt-oss and others).
2. **Music AI** for song and instrumental **generation**, **analysis** (stems, beats, chords, key,
   structure) and **transcription and scores** (audio to MIDI, sheet music, MusicXML).

Each week it writes a report (HTML, Markdown and JSON) ranking the best models it found, **whatever
their size**. Every model gets a **"Runs here?"** flag that says whether your machine can run it. A
checkbox at the top of the HTML report hides the ones that can't. Models that weren't in last week's
report are marked **NEW**. When the report is ready it can also send you a Telegram message.

## Where it looks

| Source | What it gives | Key needed? |
|---|---|---|
| Hugging Face Hub | New and trending open-weight LLMs from the major labs; music models; licences, sizes, GGUF builds | No |
| GitHub | Music tools that ship weights (Basic Pitch, Demucs, MT3, all-in-one, oemer…) | No (token raises limits) |
| YouTube | New videos from AI channels (Matthew Berman, AI Explained, Two Minute Papers, …) via RSS | No; an API key adds keyword search |
| Reddit | Top weekly posts in r/LocalLLaMA, r/LocalLLM, r/aimusic and others | No |
| Hacker News | Popular stories about open weights and music models | No |
| arXiv | New music generation, transcription and OMR research | No |
| Claude (optional) | A written briefing that searches the web for current benchmarks (LMArena, Artificial Analysis…), compares the best open models with Claude and ChatGPT, and gives picks for your machine | `ANTHROPIC_API_KEY` |

### Industry rating matrix

With an `ANTHROPIC_API_KEY` set, the report opens with a rating matrix. It scores the top models
1–5 in each capability area and puts the leading paid products in the same table for comparison:

| Group | Compared with | Areas scored |
|---|---|---|
| Open LLMs | Claude, ChatGPT, Gemini | Coding, Reasoning & maths, Knowledge, Writing & chat, Tools & agents, Multilingual, Long context, Vision |
| Music generation | Suno, Udio | Vocals, Instrumentals, Song structure, Lyrics adherence, Control & editing, Audio fidelity |
| Music analysis | Leading paid analysis service | Accuracy, Robustness, Coverage, Outputs, Ease of use |
| Transcription & scores | Leading paid transcription tool | Accuracy, Robustness, Coverage, Outputs, Ease of use |

5 means it matches the best paid product in that area, 3 means solid but clearly behind, and a dash
means it doesn't apply or there's no evidence. Each row also says what the model **excels at**,
where it **falls short**, how confident the rating is, and links to the sources used.

Claude researches the scores with web search (leaderboards, benchmark tables, reviews). Each model
is researched about once a month (`[ratings] max_age_days`), so most weeks only new models cost
anything. The ratings are AI-researched summaries of public evidence, not lab measurements; low
confidence means the evidence was thin.

If a model is mentioned in this week's videos or posts, its ranking goes up, and the report says
how often it was mentioned.

## Setup (Windows)

Requires Python 3.11 or later.

```powershell
cd ai-model-scout
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # only needed for the Claude briefing
copy config.example.toml config.toml            # then set your GPU VRAM and RAM
copy .env.example .env                          # then add any keys you have (all optional)
.venv\Scripts\python -m scout --open            # first run; opens the report
.\scripts\Install-ScoutTask.ps1                 # run it every Sunday at 07:00
```

If the machine is off at the scheduled time, the task runs the next time it starts up. To pick a
different day or time, run `.\scripts\Install-ScoutTask.ps1 -Day Saturday -Time 09:30`.

To update to the latest version later (your `config.toml`, `.env` and reports are kept):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Update-Scout.ps1
```

## Setup (Linux / macOS)

```bash
cd ai-model-scout
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml && cp .env.example .env
.venv/bin/python -m scout
scripts/install-cron.sh            # Sundays 07:00
```

## Or run it in GitHub's cloud

`.github/workflows/ai-model-scout.yml` runs the scout every Sunday on GitHub Actions, so your
machine doesn't need to be on. It commits each report to `ai-model-scout/reports/` and also
attaches the report to the run. Put your keys in the repo's **Actions secrets**. Note that Reddit
often blocks GitHub's servers; when that happens, the report lists Reddit under failed sources and
everything else still works.

## Configure

Everything lives in `config.toml`:

- `[machine]`: VRAM, RAM, and `unified_memory = true` for Apple Silicon. **Set these first.**
  Every "fits / doesn't fit" verdict in the report is based on them.
- `[report]`: how far back to look, how many rows to show, and options to hide gated or
  non-commercial models.
- `[huggingface] llm_authors`: the labs whose new releases are always checked.
- `[huggingface] music_searches`, `[github] music_queries`: the music search terms.
- `[youtube] channels`: channel `@handles`, plus the keywords a video title must contain to be kept.
- `[analyst]`: turn the Claude briefing on or off, and set the model and effort.

The models in `scout/watchlist.py` are always included, even in a quiet week, so you can see when
the music tools you rely on get updated.

## How "fits your machine" is worked out

For LLMs, the scout estimates the memory needed for the weights at FP16, Q8 and Q4 (GGUF Q4_K_M),
plus about 1.5 GB for context. The "Runs here?" column then says:

- **Yes, on GPU**: fits entirely in VRAM at the format shown in the notes.
- **Yes, GPU + RAM**: a mixture-of-experts model that fits in VRAM plus system RAM at Q4. MoE
  models only use a few billion parameters per token, so they stay usable when partly in RAM
  (e.g. gpt-oss-120b, Qwen3-30B-A3B).
- **Yes, but slowly**: a dense model that only fits by spilling into system RAM. Expect a few
  tokens per second.
- **No, too big**: still listed, so you can see what the best open models are.
- **Probably (check card)**: the size isn't published (common for GitHub tools).

Music models are assumed to run unquantised (FP16) in PyTorch. These are estimates, so check the
model card before buying hardware.

The report also flags each model's licence. Many music models (for example the MusicGen weights)
are **non-commercial**. Models marked "accept terms on Hugging Face" are free to download, but you
have to click through a licence first.

## Running the models

The report tells you which models to try. To run them:

- **LLMs**: [LM Studio](https://lmstudio.ai) or [Ollama](https://ollama.com) (easiest), or llama.cpp.
  Look for the GGUF build the report mentions.
- **Music generation**: most models come with a Gradio app or a ComfyUI node. Follow the README in
  the linked repo.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The tests never touch the network: every source is answered with canned API responses, so they
also run offline.
