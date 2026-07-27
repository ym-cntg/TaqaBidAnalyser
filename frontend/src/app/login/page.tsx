"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { setIdentity } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setIdentity({ name: name.trim(), email: email.trim() });
    router.push("/projects");
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-app-gradient p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[oklch(0.62_0.15_190)] shadow-sm shadow-primary/30">
            <Zap className="h-6 w-6 text-primary-foreground" fill="currentColor" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">TAQA Bid Analyzer</h1>
            <p className="text-sm text-muted-foreground mt-1">
              AI-driven commercial bid analysis for TAQA/ADDC procurement
            </p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-border/60 bg-card shadow-sm p-6 space-y-4"
        >
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Name
            </label>
            <input
              autoFocus
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Email (optional)
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@taqa.ae"
              className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <Button type="submit" className="w-full" disabled={!name.trim()}>
            Continue
          </Button>
          <p className="text-xs text-muted-foreground text-center">
            Demo sign-in — no password, just sets who's working on this so the app can label
            template locks and audit trails correctly.
          </p>
        </form>
      </div>
    </div>
  );
}
