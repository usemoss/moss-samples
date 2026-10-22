import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "J.A.R.V.I.S. — Second Brain",
  description: "A voice-activated AI assistant with a Moss-powered persistent memory.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
