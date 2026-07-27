"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getProjectDetail, type Project } from "@/lib/api";

interface ProjectContextValue {
  project: Project | null;
  loading: boolean;
  refresh: () => void;
}

const ProjectContext = createContext<ProjectContextValue>({
  project: null,
  loading: true,
  refresh: () => {},
});

export function ProjectProvider({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  function refresh() {
    setLoading(true);
    getProjectDetail(projectId)
      .then(setProject)
      .catch(() => setProject(null))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  return (
    <ProjectContext.Provider value={{ project, loading, refresh }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useCurrentProject() {
  return useContext(ProjectContext);
}
