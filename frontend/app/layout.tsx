import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "IC Group — договоры" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
