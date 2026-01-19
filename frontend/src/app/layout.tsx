import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Providers } from "@/components/Providers";
import { EmbedMode } from "@/components/EmbedMode";
import { NavBar } from "@/components/NavBar";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "VN Bond Lab",
  description: "Vietnam bond research lab (local)",
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
              <div className="mb-6">
                <div className="glass-card rounded-2xl px-6 py-4">
                  <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-3">
                      <div className="text-white font-bold text-lg">VN Bond Lab</div>
                      <div className="text-white/40 text-sm hidden sm:block">
                        Lab nghiên cứu thị trường trái phiếu
                      </div>
                    </div>
                    <nav className="w-full sm:w-auto">
                      <NavBar />
                    </nav>
                  </div>
                </div>
              </div>
              {children}
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
