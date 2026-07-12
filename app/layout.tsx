import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Quantum Agent · 可信量子物理教学智能体",
  description: "面向大学量子物理课程的可信教学智能体：概念、推导、计算实验与课程项目。",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.css" integrity="sha384-zh0CIslj+VczCZtlzBcjt5ppRcsErDnxHjf3vLM6K2o3hI5sG0ErQG0i26Mq181X" crossOrigin="anonymous" />
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.js" integrity="sha384-Rmaq2KhO2Thw1MU5+R8vJCyk1OGx43zzLcIgDeLxzDf0PqThhfTEvxMOmPY2kNVR" crossOrigin="anonymous" />
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/contrib/auto-render.min.js" integrity="sha384-hCXGrW6PitJEwbkoStFQoQ8y07pR4v8huV4sglYcQ26QiFMRhEGHEGcRETQSnU3h" crossOrigin="anonymous" />
        <script dangerouslySetInnerHTML={{ __html: `
          document.addEventListener("DOMContentLoaded", function() {
            renderMathInElement(document.body, {
              delimiters: [
                {left: "$$", right: "$$", display: true},
                {left: "$", right: "$", display: false},
                {left: "\\\\(", right: "\\\\)", display: false},
                {left: "\\\\[", right: "\\\\]", display: true}
              ],
              throwOnError: false
            });
          });
        `}} />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
