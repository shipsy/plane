import { APIService } from "../api.service";

export class IssueCustomPropertyService extends APIService {
  constructor() {
    super("issue-custom-property");
  }

  async getIssueTypeProperties(workspaceSlug: string, projectId: string, issueTypeId?: string) {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issue-custom-properties/issue-type-properties/`, {
      params: {
        project_id: projectId,
        issue_type_id: issueTypeId,
      },
    }).then((response) => response?.data);
  }
}

export const issueCustomPropertyService = new IssueCustomPropertyService();
