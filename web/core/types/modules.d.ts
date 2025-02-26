// Type declarations for external modules
declare module "next/navigation" {
  export function useParams(): { workspaceSlug?: string };
}

declare module "@plane/types" {
  export type TIssue = any;
  export type TIssueGroupByOptions = any;
  export type TIssueOrderByOptions = any;
}

declare module "@plane/ui" {
  export const TOAST_TYPE: { ERROR: string };
  export function setToast(props: any): void;
}

declare module "@/components/issues/issue-layouts/utils" {
  export type GroupDropLocation = any;
  export function handleGroupDragDrop(
    source: any,
    destination: any,
    getIssueById: any,
    getIssueIds: any,
    updateIssueOnDrop: any,
    groupBy: any,
    subGroupBy: any,
    orderByNotSortOrder: boolean
  ): Promise<void>;
}
