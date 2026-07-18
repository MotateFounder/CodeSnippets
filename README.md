# CodeSnippets

CodeSnippets is a Tkinter desktop application for working with source files, snippets, notes, reusable prompts, reports, and local or remote LLM chat.

The app is designed around one practical idea: keep project context close, make it easy to select only the code that matters, and send clear prompts to an assistant without losing your workspace history.

## Status

CodeSnippets currently focuses on:

- session-based coding workspaces
- file browsing and editing
- snippet collection and snippet management
- assistant chat
- plain-text notebooks
- prompt management
- activity report generation
- local Llama.cpp or OpenRouter-backed LLM calls

## Requirements

Required:

- Python 3.9 or newer
- Tkinter
- `requests`

Optional:

- [RepoLens](https://github.com/MotateFounder/RepoLens) executable for workspace indexing, context retrieval, and go-to-definition support
- [Llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` for local GGUF model inference
- GGUF models in `src/assets/llmmodels/`
- OpenRouter API key for remote model access

Install Python dependencies with:

```bash
python -m pip install -r requirements.txt
```

On Linux, Tkinter may need to be installed through the system package manager:

```bash
sudo apt-get install python3-tk python3-venv
```

## Resource Install Scripts

Folder-agnostic setup scripts are provided in `scripts/`. They resolve the repository root from their own location, so the project folder can be moved later.

Windows 10:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_resources_w10.ps1
```

Windows 11:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_resources_w11.ps1
```

Linux:

```bash
bash ./scripts/install_resources_linux.sh
```

macOS:

```bash
bash ./scripts/install_resources_macos.sh
```

The scripts:

- create `.venv`
- install `requirements.txt`
- create expected asset folders
- optionally download Llama.cpp, RepoLens, and a GGUF model if URLs are supplied

Optional Windows example:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_resources_w11.ps1 `
  -LlamaCppZipUrl "https://example.com/llamacpp.zip" `
  -RepoLensExeUrl "https://example.com/repolens.exe" `
  -ModelUrl "https://example.com/model.gguf"
```

Optional Linux/macOS example:

```bash
LLAMACPP_ZIP_URL="https://example.com/llamacpp.zip" \
REPOLENS_BIN_URL="https://example.com/repolens" \
MODEL_URL="https://example.com/model.gguf" \
bash ./scripts/install_resources_linux.sh
```

## Run

Windows:

```powershell
.\.venv\Scripts\python.exe .\app.py
```

or, without a virtual environment:

```powershell
python .\app.py
```

Linux/macOS:

```bash
./.venv/bin/python ./app.py
```

or:

```bash
python3 ./app.py
```

## Main Workflow

### 1. Start A Session

Launch `app.py`. The splash screen lets you create, open, edit, archive, and unarchive workspace sessions.

When creating or editing a session, you can configure:

- session name
- repository folder
- description
- optional icon
- RepoLens include/exclude paths
- local Llama.cpp launch preference
- local model path
- context window

The splash screen and main toolbar open the same reusable Settings window.

### 2. Browse And Edit Files

The left panel contains:

- repository file explorer
- refresh button
- new file button
- progressive search engine
- search results tree

Search results appear progressively instead of waiting for the full search to finish. Search priority is:

1. currently open files
2. files referenced by selected snippets
3. the rest of the workspace

Search cancellation is thread-safe, and UI updates are handled only on the Tk main thread.

Double-click a file to open it. The editor supports:

- syntax coloring
- line selection
- save with backup
- right-click editor actions
- F12 go-to-definition through RepoLens when available

### 3. Collect Snippets

Snippets are collected from selected source ranges or entered manually.

The snippet area supports:

- selected-snippet context
- source jumping
- collapse/expand cards
- snippet clipboards
- snippet categories
- improved Snippets Manager popup

The Snippets Manager stays open while browsing snippets. Double-clicking a snippet no longer closes the manager; selecting a snippet and clicking Open opens it and closes the popup.

### 4. Chat With CodeSnippets

The assistant chat supports:

- streaming responses
- local Llama.cpp-compatible APIs
- OpenRouter
- chat branching
- chat renaming
- chat deletion
- categorized Chat Manager views
- session-scoped chat history

All LLM calls go through a FIFO queue. The queue keeps requests serialized and avoids concurrent execution through the same app queue. Streaming is enabled for queued inquiries.

Useful prompt/context patterns include:

```text
/explain
/fix
/change
/review
/write
/research
@snippet_name
#file:'path/to/file'
#filetree
```

## Notebook

The Notebook tab is session-agnostic and stores plain-text notebooks/pages locally.

Features:

- two-column notebook/page layout
- notebook color markers
- page list search
- editable title and body
- notebook/page create, rename, duplicate, and delete
- right-click menus
- delete confirmation
- local JSON persistence
- autosave
- copy/cut/paste in note text
- basic formatting controls for bold, italic, and bullet-style text
- `@` references to snippets, with double-click navigation where supported

Notebook data is stored under:

```text
src/services/notebook/data/
```

That folder is ignored by Git because it contains local user data.

## Prompt Manager

Prompt Manager is a lightweight prompt notebook for reusable prompt templates.

Features:

- prompt notebooks
- prompt list search
- prompt create, rename, duplicate, and delete
- editable prompt name
- multiline prompt editor
- explicit Save behavior
- Copy template
- Copy completed prompt
- Clear variables
- right-click menus
- local JSON persistence

Variables are detected in either form:

```text
{{variable name}}
[variable name]
```

Variable names may contain spaces. Repeated variables are replaced consistently.

Variable fields support normal text and `@` references, including:

```text
@snippet:MySnippet
@file:path/to/file.py
@symbol:ClassName.method_name
```

Unresolved references are preserved and reported clearly.

Prompt Manager data is stored under:

```text
src/services/promptManager/data/
```

That folder is ignored by Git because it contains local user data.

## Write Report

The Write Report feature generates a plain-text activity report from notes and chat messages within a selected time period.

The dialog supports:

- from/to date and time
- bullet limit
- optional summary
- destination folder picker
- editable report prompt template
- streaming LLM output preview
- cancellation before saving
- UTF-8 `.txt` report output

The report prompt template is visible and editable in the dialog. The collected notes and chat evidence are sent separately to the LLM and are not shown in that template area.

Reports are generated through the existing LLM queue as background work.

## Settings

Settings are intentionally simple by default.

Default Settings view:

- Appearance
  - Theme
- Model & Provider
  - Provider
  - Use local Llama.cpp server
  - Context window
  - Local model
  - Model path
  - Local server URL
  - OpenRouter model
  - OpenRouter API key
- Chat
  - Context instruction

The bottom-left `Advanced mode` checkbox reveals advanced controls, except audio settings, which have been removed.

Advanced mode exposes:

- text sizes
- color overrides
- advanced Llama.cpp launch flags
- request timeout and provider internals
- context retrieval settings
- RepoLens and Smart Context tuning
- prompt and reasoning internals

The old individual "show advanced..." checkboxes have been removed.

## Local Llama.cpp

CodeSnippets starts with a safe local llama.cpp configuration suitable for smaller models and modest PCs:

```text
--ctx-size 8192
--n-gpu-layers 0
--parallel 1
--flash-attn off
--fit off
```

By default, CodeSnippets selects the smallest bundled GGUF model in `src/assets/llmmodels/`.

Advanced mode lets users override these settings and experiment with larger context windows, GPU offload, KV cache options, speculative decoding, MoE options, and server sampling options.

The Model & Provider page includes a `Reload model with new configuration` button. It is enabled only after relevant local Llama.cpp settings change. Clicking it saves the current settings, stops the running llama-server process, and relaunches it with the new configuration.

## RepoLens

RepoLens is optional but recommended for:

- workspace indexing
- context retrieval
- go-to-definition
- Smart Context support

Expected location:

```text
src/services/repoLens/repolens.exe
```

or platform equivalent:

```text
src/services/repoLens/repolens
```

RepoLens generated databases are stored under:

```text
src/services/repoLens/databases/
```

External RepoLens binaries, libraries, and generated databases are ignored by Git.

## Storage Map

```text
settings.json
users/sessions/
src/services/notebook/data/
src/services/promptManager/data/
src/services/repoLens/databases/
src/assets/llmmodels/
src/assets/LlamaCPP/
downloads/
```

These paths contain local state, downloaded binaries, generated indexes, or large model files and should not be committed.

## Git Hygiene

The `.gitignore` excludes:

- local settings
- session data
- notebook and prompt-manager data
- Python caches and virtual environments
- LLM model files
- Llama.cpp distribution contents
- RepoLens external binaries/libraries
- RepoLens generated databases
- downloaded archives

Lightweight source files such as RepoLens service wrappers and README files remain trackable.

## Notes

- CodeSnippets is language agnostic.
- RepoLens improves code navigation and context quality but is optional.
- Local Llama.cpp is optional; OpenRouter can be used instead.
- The app favors local JSON persistence and does not require a database server.
- Large external assets should be installed locally through scripts or manual download, not committed to the repository.
