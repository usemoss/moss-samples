from __future__ import annotations

import json
import logging
import platform
import threading
import time
from pathlib import Path
from typing import Any

import webview
from pynput import keyboard

import ai
from capture import capture_screen_data_url
from memory import StudyMemory, title_from_explanation
from settings import load_settings, public_settings, save_settings


ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "overlay.html"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger("studyoverlay")


class StudyOverlayApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.memory = StudyMemory()
        self.busy = False

    def set_window(self, window: webview.Window) -> None:
        self.window = window

    def get_settings(self) -> dict[str, Any]:
        return public_settings()

    def save_settings(self, values: dict[str, str]) -> dict[str, Any]:
        save_settings(values)
        self.memory.reload()
        return public_settings()

    def hide_window(self) -> None:
        if self.window:
            self.window.hide()

    def show_window(self) -> None:
        if self.window:
            self.window.show()

    def run_capture(self, user_prompt: str = "") -> dict[str, Any]:
        if self.busy:
            return {"ok": False, "error": "StudyOverlay is already working on a capture."}

        if not load_settings().get("OPENROUTER_API_KEY"):
            return {"ok": False, "error": "Add your OpenRouter API key in settings first.", "settings": True}

        self.busy = True
        memory_result = None
        try:
            image_data_url = self._capture_without_overlay()
            memory_query = user_prompt.strip() or "study material, concept, formula, question, answer, explanation visible on screen"
            memory_result = self.memory.related_context(memory_query, top_k=3)
            explanation = ai.explain_screenshot(image_data_url, memory_result.context, user_prompt)
            self.memory.remember(explanation, title_from_explanation(explanation))
            return {
                "ok": True,
                "markdown": explanation,
                "used_context": memory_result.used,
                "memory_warning": memory_result.warning,
            }
        except Exception as exc:
            LOGGER.exception("Capture flow failed")
            warning = memory_result.warning if memory_result else ""
            return {"ok": False, "error": str(exc), "memory_warning": warning}
        finally:
            self.busy = False

    def _capture_without_overlay(self) -> str:
        if self.window:
            try:
                self.window.hide()
                time.sleep(0.16)
            except Exception:
                pass

        try:
            return capture_screen_data_url()
        finally:
            if self.window:
                try:
                    self.window.show()
                except Exception:
                    pass


def js_call(window: webview.Window, function_name: str, payload: dict[str, Any] | None = None) -> None:
    arg = "" if payload is None else json.dumps(payload)
    window.evaluate_js(f"window.StudyOverlay.{function_name}({arg})")


def hotkey_string() -> str:
    if platform.system() == "Darwin":
        return "<cmd>+<shift>+a"
    return "<ctrl>+<shift>+a"


def _mac_accessibility_trusted() -> bool:
    if platform.system() != "Darwin":
        return True
    try:
        from Quartz import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def start_hotkey_listener(api: StudyOverlayApi) -> bool:
    if not _mac_accessibility_trusted():
        LOGGER.warning("Global hotkey disabled until Accessibility permission is granted.")
        return False

    def on_activate() -> None:
        if api.window is None:
            return
        js_call(api.window, "hotkeyStarted")

        def worker() -> None:
            result = api.run_capture()
            if api.window:
                js_call(api.window, "hotkeyFinished", result)

        threading.Thread(target=worker, daemon=True).start()

    listener = keyboard.GlobalHotKeys({hotkey_string(): on_activate})
    try:
        listener.start()
    except Exception as exc:
        LOGGER.warning("Global hotkey disabled: %s", exc)
        return False

    LOGGER.info("Global hotkey registered: %s", hotkey_string())
    return True


def on_loaded(api: StudyOverlayApi) -> None:
    hotkey_enabled = start_hotkey_listener(api)
    if api.window:
        js_call(
            api.window,
            "bootstrap",
            {
                "settings": public_settings(),
                "hotkey": hotkey_string(),
                "hotkey_enabled": hotkey_enabled,
            },
        )


def main() -> None:
    api = StudyOverlayApi()
    window = webview.create_window(
        "StudyOverlay",
        str(HTML_PATH),
        js_api=api,
        width=760,
        height=430,
        x=70,
        y=80,
        frameless=True,
        transparent=True,
        on_top=True,
        easy_drag=False,
        resizable=True,
        background_color="#000000",
    )
    api.set_window(window)
    webview.settings["DRAG_REGION_SELECTOR"] = ".drag-handle"
    webview.start(on_loaded, api, debug=False)


if __name__ == "__main__":
    main()
