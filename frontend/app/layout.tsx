import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { Nav } from "./components/nav";

const geist = Geist({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-geist",
});

export const metadata: Metadata = {
  title: "Essence of Pi",
  description: "Research papers, distilled into 3blue1brown-style explainers.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.85em%22 font-size=%2290%22 fill=%22white%22>π</text></svg>",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={geist.variable}>
      <body className="relative min-h-screen overflow-x-hidden">
        <Nav />
        {children}
      </body>
    </html>
  );
}
