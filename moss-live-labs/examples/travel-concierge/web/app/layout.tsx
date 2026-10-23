import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "@livekit/components-styles";
import "./globals.css";

export const metadata: Metadata = {
  title: "Wander · Travel Concierge",
  description: "A voice travel concierge powered by Moss — a pre-loaded catalog plus a live session.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
