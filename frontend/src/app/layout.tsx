import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Power BI MCP Autonomous Agent",
  description: "Enterprise-Ready Interface for Power BI Model Context Protocol servers",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
