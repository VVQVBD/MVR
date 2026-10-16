import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "IC Group — Закрытие месяца",
  description: "Операционная консоль IC Group для сверки смен и выплат",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="ru"><body className="min-h-screen"><Providers>{children}</Providers></body></html>;
}
