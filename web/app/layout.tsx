import type { Metadata } from "next";
import { Figtree, Geist_Mono } from "next/font/google";

import { AppHeader } from "@/components/shell/AppHeader";
import { StatusBanner } from "@/components/shell/StatusBanner";

import { Providers } from "./providers";
import "./globals.css";

// UI grotesk + monospace readouts (design tokens, docs/proposals/WS3-design-tokens.md). Self-hosted by next/font.
const figtree = Figtree({
  variable: "--font-figtree",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Beatopia",
  description: "Find, chop and flip Creative Commons samples.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`dark ${figtree.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-background font-sans text-foreground">
        <Providers>
          <AppHeader />
          <StatusBanner />
          {children}
        </Providers>
      </body>
    </html>
  );
}
