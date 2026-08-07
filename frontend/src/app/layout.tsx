import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TAQA Bid Analyzer — Maximo",
  description: "Bid analysis for TAQA/ADDC procurement, built against real Maximo data",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full bg-background text-foreground">
        <nav className="border-b border-border/60 bg-card px-6 py-3">
          <div className="mx-auto flex max-w-6xl items-center gap-4">
            <span className="text-sm font-semibold">TAQA Bid Analyzer</span>
            <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
              Projects
            </Link>
            <Link href="/rfqs" className="text-sm text-muted-foreground hover:text-foreground">
              Browse RFQs
            </Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
