import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { ChatWidget } from "@/components/ChatWidget";
import { SiteHeader } from "@/components/SiteHeader";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Marketplace",
  description: "Buyer storefront for the marketplace platform",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
          {children}
        </main>
        <footer className="border-t border-border/80 py-8">
          <div className="mx-auto max-w-5xl px-4 text-sm text-muted-foreground sm:px-6">
            Marketplace — a storefront demo.
          </div>
        </footer>
        <ChatWidget />
      </body>
    </html>
  );
}
