import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "@livekit/components-styles";
import "./globals.css";

export const metadata: Metadata = {
  title: "Moss · Support Voice Agent",
  description: "A customer-support voice agent grounded in a Moss knowledge base.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
