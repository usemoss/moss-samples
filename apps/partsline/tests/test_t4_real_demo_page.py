from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME_PAGE = ROOT / "app" / "page.tsx"
DEMO_CLIENT = ROOT / "app" / "PartsLineDemoClient.tsx"


class T4RealDemoPageStaticContractTest(unittest.TestCase):
    def test_root_demo_route_files_exist(self) -> None:
        self.assertTrue(HOME_PAGE.exists())
        self.assertTrue(DEMO_CLIENT.exists())

    def test_root_page_renders_real_demo_client(self) -> None:
        source = HOME_PAGE.read_text(encoding="utf-8")

        self.assertIn("PartsLineDemoClient", source)
        self.assertIn("export default function HomePage", source)
        self.assertNotIn("VoiceTestClient", source)

    def test_demo_client_reuses_livekit_connection_flow(self) -> None:
        source = DEMO_CLIENT.read_text(encoding="utf-8")
        source_without_whitespace = "".join(source.split())

        self.assertIn('"use client"', source)
        self.assertIn("type AudioCaptureOptions", source)
        self.assertIn("AUDIO_CAPTURE_OPTIONS", source)
        self.assertIn("echoCancellation: true", source)
        self.assertIn("noiseSuppression: true", source)
        self.assertIn("autoGainControl: true", source)
        self.assertIn("new Room({", source)
        self.assertIn("audioCaptureDefaults: AUDIO_CAPTURE_OPTIONS", source)
        self.assertIn('uniqueName("partsline-demo")', source)
        self.assertIn('fetch("/api/token"', source)
        self.assertIn("room_name", source)
        self.assertIn("participant_identity", source)
        self.assertIn(".connect(server_url, participant_token)", source)
        self.assertIn(
            "setMicrophoneEnabled(true,AUDIO_CAPTURE_OPTIONS",
            source_without_whitespace,
        )
        self.assertIn('registerTextStreamHandler("lk.transcription"', source)
        self.assertIn("lk.transcription_final", source)

    def test_demo_client_declares_one_talk_button_and_live_transcript(self) -> None:
        source = DEMO_CLIENT.read_text(encoding="utf-8")

        self.assertEqual(source.count("<button"), 1)
        self.assertIn(">Talk<", source)
        self.assertIn('aria-live="polite"', source)
        self.assertIn("transcriptLines.map", source)
        self.assertIn("RoomAudioRenderer", source)
