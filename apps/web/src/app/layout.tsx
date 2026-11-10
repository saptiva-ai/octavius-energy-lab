import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { ToasterProvider } from "../components/providers/ToasterProvider";
import { SyncProvider } from "../components/providers/SyncProvider";
import { SessionExpiredToast } from "../components/ui/SessionExpiredToast";
import { PRODUCT_NAME } from "@/lib/brand";

const inter = Inter({ subsets: ["latin"] });

// Force dynamic rendering for the entire app
export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata = {
  title: PRODUCT_NAME,
  description:
    "Unified conversational interface combining direct LLM interactions with file analysis capabilities",
  icons: {
    icon: "/saptiva_ai_logo.jpg",
    shortcut: "/saptiva_ai_logo.jpg",
    apple: "/saptiva_ai_logo.jpg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Providers>
          {children}
          <ToasterProvider />
          <SyncProvider />
          <SessionExpiredToast />
        </Providers>
      </body>
    </html>
  );
}
