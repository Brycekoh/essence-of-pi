import { PaperView } from "../../components/paper-view";

// `params` is a Promise in this version of Next -- awaiting it is the whole
// reason this page is an async server component. Everything interactive
// lives in PaperView, which is a client component.
export default async function PaperPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PaperView paperId={id} />;
}
