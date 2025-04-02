"use client";

import { API_BASE_URL } from "../../helpers/common.helper";

export const fetchCustomProperties = async (workspaceSlug: string): Promise<Record<string, string[]>> => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/workspaces/${workspaceSlug}/custom-properties/`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch custom properties: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error("Error fetching custom properties:", error);
    return {}; // Return empty object in case of error
  }
};
