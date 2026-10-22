import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SiteFooter, SiteHeader } from "../components/site-shell";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: { default: "Champions (WC 26)", template: "%s · Champions (WC 26)" },
  description: "Play Classic Wheel or World Cup Era, reveal your Squad DNA and chase a perfect 8–0 at World Cup 2026.",
  applicationName: "Champions (WC 26)",
  openGraph: {
    title: "Champions (WC 26)",
    description: "Two ways to build history. One perfect 8–0.",
    type: "website",
    images: [{ url: "/og-modes.png", width: 1200, height: 630, alt: "Champions WC 26 — Classic Wheel, World Cup Era and Moss Squad DNA" }],
  },
  twitter: { card: "summary_large_image", title: "Champions (WC 26)", description: "Two ways to build history. One perfect 8–0.", images: ["/og-modes.png"] },
  icons: { icon: "/icon" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geist.variable} ${mono.variable}`}><SiteHeader />{children}<SiteFooter /></body></html>;
}
