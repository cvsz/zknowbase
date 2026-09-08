import type { Metadata } from "next";
import { cookies } from "next/headers";
import "./globals.css";
import { LoginGate } from "@/components/LoginGate";
import { Nav } from "@/components/Nav";
import { ADMIN_SESSION_COOKIE, verifyAdminSession } from "@/lib/admin-auth";

export const metadata: Metadata = {
  title: "zknowbase Admin",
  description: "AI Knowledge Base administration",
};
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  let session = null;
  try {
    const cookieStore = await cookies();
    session = verifyAdminSession(cookieStore.get(ADMIN_SESSION_COOKIE)?.value);
  } catch (error) {
    console.error("admin_auth_configuration_error", error);
  }

  const adsenseScript = (
    <script
      async
      src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-4971034675329740"
      crossOrigin="anonymous"
    />
  );

  if (!session) {
    const oidcEnabled = Boolean((process.env.ZKB_OIDC_ISSUER ?? "").trim());
    return (
      <html lang="en">
        <head>{adsenseScript}</head>
        <body>
          <LoginGate oidcEnabled={oidcEnabled} />
        </body>
      </html>
    );
  }

  return (
    <html lang="en">
      <head>{adsenseScript}</head>
      <body>
        <div className="flex min-h-screen">
          <Nav username={session.sub} role={session.role} />
          <main className="min-w-0 flex-1 p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
