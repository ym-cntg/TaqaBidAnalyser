"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getIdentity } from "@/lib/auth";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getIdentity() ? "/projects" : "/login");
  }, [router]);

  return null;
}
