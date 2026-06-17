import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

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
      <body className="min-h-full flex bg-background text-foreground">
        <Sidebar />
        <main className="flex-1 ml-64 overflow-auto">{children}</main>
      </body>
    </html>
  );
}
