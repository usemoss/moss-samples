from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_CLIENT = ROOT / "app" / "PartsLineDemoClient.tsx"
CHIP_COMPONENT = ROOT / "app" / "LookupChip.tsx"


class T5LookupChipsPageStaticContractTest(unittest.TestCase):
    def test_demo_client_listens_for_lookup_chip_data_topic(self) -> None:
        source = DEMO_CLIENT.read_text(encoding="utf-8")

        self.assertIn("LOOKUP_CHIP_TOPIC", source)
        self.assertIn('"lookup_chip"', source)
        self.assertIn("RoomEvent.DataReceived", source)
        self.assertIn("parseLookupChipPayload", source)
        self.assertIn("new TextDecoder().decode(payload)", source)
        self.assertIn("JSON.parse", source)

    def test_demo_client_inserts_chips_into_transcript_order(self) -> None:
        source = DEMO_CLIENT.read_text(encoding="utf-8")

        self.assertIn("type TranscriptItem", source)
        self.assertIn('kind: "transcript"', source)
        self.assertIn('kind: "lookup_chip"', source)
        self.assertIn("transcriptItems.map", source)
        self.assertIn('item.kind === "lookup_chip"', source)
        self.assertIn("<LookupChip chip={item.chip}", source)
        self.assertNotIn("lookupChips", source)

    def test_lookup_chip_component_renders_labels_and_vehicle_filter(self) -> None:
        source = CHIP_COMPONENT.read_text(encoding="utf-8")

        self.assertIn('single: "Found"', source)
        self.assertIn('ambiguous: "Asking"', source)
        self.assertIn('superseded: "Replaced"', source)
        self.assertIn('no_match: "Not carried"', source)
        self.assertIn("formatVehicleFilter", source)
        self.assertIn("chip.filter.year", source)
        self.assertIn("chip.filter.make", source)
        self.assertIn("chip.filter.model", source)
        self.assertIn("chip.filter.engine", source)

    def test_lookup_chip_component_uses_payload_details_only(self) -> None:
        source = CHIP_COMPONENT.read_text(encoding="utf-8")

        self.assertIn("chip.candidates?.values", source)
        self.assertIn("chip.parts", source)
        self.assertIn("part.part_number", source)
        self.assertIn("part.price", source)
        self.assertIn("part.stock", source)
        self.assertIn('"old to new"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("lookup_part", source)
