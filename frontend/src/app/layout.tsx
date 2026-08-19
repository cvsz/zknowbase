import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = { title: "zknowbase Admin", description: "AI Knowledge Base administration" };

export default function RootLayout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body><div className="flex min-h-screen"><Nav/><main className="min-w-0 flex-1 p-8">{children}</main></div></body></html>;
}
