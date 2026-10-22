import type { Metadata } from "next";
import { GameClient } from "../../components/game/game-client";

export const metadata: Metadata = {
  title: "Draft Room · Champions (WC 26)",
  description: "Play the Classic Wheel or World Cup Era, reveal your Squad DNA and chase the perfect 8–0.",
};

export default function GamePage() {
  return <GameClient />;
}
