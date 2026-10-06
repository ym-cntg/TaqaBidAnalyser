import { UploadWorkspace } from "./upload-workspace";

// Next.js 16: dynamic route params are async.
export default async function UploadProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <UploadWorkspace projectId={id} />;
}
