"use client";

import { use } from "react";
import { ProjectProvider } from "@/lib/project-context";
import { Sidebar } from "@/components/sidebar";

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);

  return (
    <ProjectProvider projectId={projectId}>
      <div className="min-h-full flex">
        <Sidebar projectId={projectId} />
        <main className="flex-1 ml-64 min-h-screen overflow-auto bg-app-gradient">
          {children}
        </main>
      </div>
    </ProjectProvider>
  );
}
