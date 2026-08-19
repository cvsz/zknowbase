import type { Metadata } from "next";
import { cookies } from "next/headers";
import "./globals.css";
import { LoginGate } from "@/components/LoginGate";
import { Nav } from "@/components/Nav";
import { ADMIN_SESSION_COOKIE, verifyAdminSession } from "@/lib/admin-auth";

export const metadata: Metadata = { title: "zknowbase Admin", description: "AI Knowledge Base administration" };
export const dynamic = "force-dynamic";

export default function RootLayout({children}:{children:React.ReactNode}) {
  let session = null;
  try {
    session = verifyAdminSession(cookies().get(ADMIN_SESSION_COOKIE)?.value);
  } catch (error) {
    console.error("admin_auth_configuration_error", error);
  }
  if (!session) return <html lang="en"><body><LoginGate/></body></html>;
  return <html lang="en"><body><div className="flex min-h-screen"><Nav username={session.sub} role={session.role}/><main className="min-w-0 flex-1 p-8">{children}</main></div></body></html>;
}
