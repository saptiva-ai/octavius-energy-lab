"use client";

import Image from "next/image";
import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col items-center justify-center gap-10 px-4">
        {/* Logo Saptiva AI */}
        <div className="relative h-48 w-48">
          {/* Light theme logo - hidden in dark mode */}
          <Image
            src="/SaptivaAIlogo_whitebg.PNG"
            alt="Saptiva IA"
            fill
            priority
            sizes="192px"
            className="object-contain drop-shadow-[0_10px_30px_rgba(45,212,191,0.45)] dark:hidden"
          />
          {/* Dark theme logo - hidden in light mode */}
          <Image
            src="/SaptivaAIlogo_blackbg.PNG"
            alt="Saptiva IA"
            fill
            priority
            sizes="192px"
            className="object-contain drop-shadow-[0_10px_30px_rgba(45,212,191,0.45)] hidden dark:block"
          />
        </div>

        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
