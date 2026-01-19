import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Providers } from "@/components/Providers";
import { EmbedMode } from "@/components/EmbedMode";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Interest Rates Dashboard",
  description: "Track deposit and loan interest rates",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="noise-overlay">
      <body className={inter.className}>
        <Providers>
          <EmbedMode />
          <div className="min-h-screen">
            <div className="app-shell max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
              {children}
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
