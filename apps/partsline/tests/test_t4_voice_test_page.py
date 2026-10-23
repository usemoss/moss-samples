from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VOICE_PAGE = ROOT / "app" / "voice-test" / "page.tsx"
VOICE_CLIENT = ROOT / "app" / "voice-test" / "VoiceTestClient.tsx"
PACKAGE_JSON = ROOT / "package.json"


class T4VoiceTestPageStaticContractTest(unittest.TestCase):
    # No browser component harness is installed in this repo. The click -> token
    # fetch -> LiveKit room join behavior is validated by the manual voice test.
    def test_voice_test_route_files_exist(self) -> None:
        self.assertTrue(VOICE_PAGE.exists())
        self.assertTrue(VOICE_CLIENT.exists())

    def test_voice_test_page_imports_client_component(self) -> None:
        source = VOICE_PAGE.read_text(encoding="utf-8")

        self.assertIn("VoiceTestClient", source)
        self.assertIn("export default function VoiceTestPage", source)

    def test_voice_test_client_source_contains_manual_connect_flow_hooks(self) -> None:
        source = VOICE_CLIENT.read_text(encoding="utf-8")
        source_without_whitespace = "".join(source.split())

        self.assertIn('"use client"', source)
        self.assertIn("type AudioCaptureOptions", source)
        self.assertIn("AUDIO_CAPTURE_OPTIONS", source)
        self.assertIn("echoCancellation: true", source)
        self.assertIn("noiseSuppression: true", source)
        self.assertIn("autoGainControl: true", source)
        self.assertIn("new Room({", source)
        self.assertIn("audioCaptureDefaults: AUDIO_CAPTURE_OPTIONS", source)
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

    def test_voice_test_source_declares_single_connect_button_and_transcript_region(
        self,
    ) -> None:
        source = VOICE_CLIENT.read_text(encoding="utf-8")

        self.assertEqual(source.count("<button"), 1)
        self.assertIn(">Connect<", source)
        self.assertIn('aria-live="polite"', source)
        self.assertIn("Transcript", source)

    def test_voice_test_client_resets_ui_when_livekit_room_disconnects(
        self,
    ) -> None:
        source = VOICE_CLIENT.read_text(encoding="utf-8")

        self.assertIn("RoomEvent", source)
        self.assertIn("RoomEvent.Disconnected", source)
        self.assertIn("RoomEvent.ParticipantDisconnected", source)
        self.assertIn("setRoom(null)", source)
        self.assertIn('setStatus("Idle")', source)
        self.assertIn(".off(RoomEvent.Disconnected", source)
        self.assertIn(".off(RoomEvent.ParticipantDisconnected", source)

    def test_package_manifest_declares_approved_web_stack(self) -> None:
        source = PACKAGE_JSON.read_text(encoding="utf-8")

        self.assertIn('"next"', source)
        self.assertIn('"react"', source)
        self.assertIn('"react-dom"', source)
        self.assertIn('"livekit-client"', source)
        self.assertIn('"@livekit/components-react"', source)
        self.assertNotIn('"pipecat"', source)
        self.assertNotIn('"vapi"', source)
        self.assertNotIn('"retell"', source)
