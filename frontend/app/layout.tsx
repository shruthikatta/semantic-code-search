import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Semantic Code Search",
  description: "Hybrid (BM25 + dense vector) search over Python code.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
