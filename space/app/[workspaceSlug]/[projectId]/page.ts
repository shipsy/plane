import { notFound, redirect } from "next/navigation";
// types
import { TProjectPublishSettings } from "@plane/types";
// services
import PublishService from "@/services/publish.service";

const publishService = new PublishService();

type Props = {
  params: Promise<{
    workspaceSlug: string;
    projectId: string;
  }>;
  searchParams: Promise<any>;
};

export default async function IssuesPage(props: Props) {
  const { params, searchParams } = props;
  // query params - await the params
  const { workspaceSlug, projectId } = await params;
  const { board, peekId } = await searchParams;

  let response: TProjectPublishSettings | undefined = undefined;
  try {
    response = await publishService.fetchAnchorFromProjectDetails(workspaceSlug, projectId);
  } catch (error) {
    // redirect to 404 page on error
    notFound();
  }

  let url = "";
  if (response?.entity_name === "project") {
    url = `/issues/${response?.anchor}`;
    const urlParams = new URLSearchParams(); // Renamed to avoid conflict with params
    if (board) urlParams.append("board", board);
    if (peekId) urlParams.append("peekId", peekId);
    if (urlParams.toString()) url += `?${urlParams.toString()}`;
    redirect(url);
  } else {
    notFound();
  }
}