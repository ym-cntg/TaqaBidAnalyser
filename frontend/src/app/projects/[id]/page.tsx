import { ProjectDetailClient } from "./project-detail-client";

// Next.js 16: dynamic route params are async.
export default async function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectDetailClient projectId={id} />;
}
