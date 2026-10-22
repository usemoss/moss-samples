import type { Metadata } from "next";
import { ScoutLabClient } from "../../components/scout/scout-lab-client";

export const metadata: Metadata = {
  title: "Moss Scout Lab · Champions (WC 26)",
  description: "Search and browse 10,973 World Cup player campaigns with Moss semantic retrieval.",
};

export default function ScoutPage() {
  return <ScoutLabClient />;
}
