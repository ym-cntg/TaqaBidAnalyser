import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthGate } from "@/components/auth-gate";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TAQA Bid Analyzer",
  description: "AI-driven commercial bid analysis for TAQA/ADDC procurement",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full bg-background text-foreground">
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
