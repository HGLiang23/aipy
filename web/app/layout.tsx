import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIPY 内容工作台",
  description: "面向小团队的 AI 内容生产工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
