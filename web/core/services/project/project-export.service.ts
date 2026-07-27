import { API_BASE_URL } from "@/helpers/common.helper";
import { APIService } from "@/services/api.service";
// helpers

export class ProjectExportService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async csvExport(
    workspaceSlug: string,
    data: {
      provider: string;
      project: string[];
      multiple?: boolean;
    },
    filterParams?: Record<string, any>
  ): Promise<any> {
    return this.post(`/api/workspaces/${workspaceSlug}/export-issues/`, data, {
      params: filterParams,
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getExportsServicesList(
    workspaceSlug: string,
    cursor: string,
    per_page: number = 10
  ): Promise<any> {
    return this.get(`/api/workspaces/${workspaceSlug}/export-issues/`, {
      params: { cursor, per_page },
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

}
