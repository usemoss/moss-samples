# StudyOverlay

StudyOverlay is a Python desktop overlay study assistant. It creates an always-on-top transparent pywebview panel, captures the current screen with `mss`, sends the screenshot to a vision-capable OpenRouter chat model, renders the tutor response as Markdown, and typesets math with KaTeX.

Moss is used as real-time semantic session memory. Each generated explanation is added to a local `study-session` index, and later captures can include related earlier explanations as context. The Python app uses the official Moss JavaScript runtime as a local sidecar by default, with the Python SDK as a fallback path. If Moss credentials are missing or invalid, the app logs a warning and continues without memory.

## Setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   pnpm install
   ```

3. Run the app:

   ```bash
   python main.py
   ```

4. On first launch, enter your OpenRouter API key and optional Moss credentials in the overlay settings view. The app saves them to your local user data directory, not to the repository. Moss credentials come from signing up at [moss.dev](https://moss.dev/).

## Usage

- macOS hotkey: `Cmd+Shift+A`
- Windows/Linux hotkey: `Ctrl+Shift+A`
- The gear button reopens settings so keys can be updated or cleared without hand-editing files.
- Leave Moss fields blank to run without semantic memory.
- If `node` is not on your PATH, set `STUDYOVERLAY_NODE=/path/to/node`. In this Codex workspace, the app automatically finds the bundled Node runtime.

## Notes

- macOS may ask for Screen Recording and Accessibility permissions for screen capture and global hotkeys.
- OpenRouter image requests are sent as `data:image/png;base64,...` image inputs to the chat completions endpoint.
- Local credentials are stored in `config.json` under the app user data folder and are excluded by `.gitignore`.
