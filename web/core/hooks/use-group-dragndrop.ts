"use client";

import { useParams } from "next/navigation";
import { TIssue, TIssueGroupByOptions, TIssueOrderByOptions } from "@plane/types";
import { TOAST_TYPE, setToast } from "@plane/ui";
import { GroupDropLocation, handleGroupDragDrop } from "@/components/issues/issue-layouts/utils";
import { EIssuesStoreType } from "@/constants/issue";
import { ISSUE_FILTER_DEFAULT_DATA } from "@/store/issue/helpers/base-issues.store";
import { useIssueDetail, useIssues } from "./store";
import { useIssuesActions } from "./use-issues-actions";

type DNDStoreType =
  | EIssuesStoreType.PROJECT
  | EIssuesStoreType.MODULE
  | EIssuesStoreType.CYCLE
  | EIssuesStoreType.PROJECT_VIEW
  | EIssuesStoreType.DRAFT
  | EIssuesStoreType.PROFILE
  | EIssuesStoreType.ARCHIVED
  | EIssuesStoreType.WORKSPACE_DRAFT;

export const useGroupIssuesDragNDrop = (
  storeType: DNDStoreType,
  orderBy: TIssueOrderByOptions | undefined,
  groupBy: TIssueGroupByOptions | undefined,
  subGroupBy?: TIssueGroupByOptions
) => {
  const { workspaceSlug } = useParams();

  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const { updateIssue } = useIssuesActions(storeType);
  const {
    issues: { getIssueIds, addCycleToIssue, removeCycleFromIssue, changeModulesInIssue },
  } = useIssues(storeType);

  /**
   * update Issue on Drop, checks if modules or cycles are changed and then calls appropriate functions
   * @param projectId
   * @param issueId
   * @param data
   * @param issueUpdates
   */
  const updateIssueOnDrop = async (
    projectId: string,
    issueId: string,
    data: Partial<TIssue>,
    issueUpdates: {
      [groupKey: string]: {
        ADD: string[];
        REMOVE: string[];
      };
    }
  ) => {
    const errorToastProps = {
      type: TOAST_TYPE.ERROR,
      title: "Error!",
      message: "Error while updating issue",
    };
    const moduleKey = ISSUE_FILTER_DEFAULT_DATA["module"];
    const cycleKey = ISSUE_FILTER_DEFAULT_DATA["cycle"];

    const isModuleChanged = Object.keys(data).indexOf(moduleKey.toString()) !== -1;
    const isCycleChanged = Object.keys(data).indexOf(cycleKey.toString()) !== -1;

    if (isCycleChanged && workspaceSlug) {
      const cycleKeyStr = cycleKey.toString();
      if (data[cycleKeyStr as keyof typeof data]) {
        addCycleToIssue(workspaceSlug.toString(), projectId, data[cycleKeyStr as keyof typeof data]?.toString() ?? "", issueId).catch(() =>
          setToast(errorToastProps)
        );
      } else {
        removeCycleFromIssue(workspaceSlug.toString(), projectId, issueId).catch(() => setToast(errorToastProps));
      }
      delete data[cycleKeyStr as keyof typeof data];
    }

    if (isModuleChanged && workspaceSlug) {
      const moduleKeyStr = moduleKey.toString();
      if (issueUpdates[moduleKeyStr]) {
        changeModulesInIssue(
          workspaceSlug.toString(),
          projectId,
          issueId,
          issueUpdates[moduleKeyStr].ADD,
          issueUpdates[moduleKeyStr].REMOVE
        ).catch(() => setToast(errorToastProps));
        delete data[moduleKeyStr as keyof typeof data];
      }
    }

    updateIssue && updateIssue(projectId, issueId, data).catch(() => setToast(errorToastProps));
  };

  const handleOnDrop = async (source: GroupDropLocation, destination: GroupDropLocation) => {
    if (
      source.columnId &&
      destination.columnId &&
      destination.columnId === source.columnId &&
      destination.id === source.id
    )
      return;

    await handleGroupDragDrop(
      source,
      destination,
      getIssueById,
      getIssueIds,
      updateIssueOnDrop,
      groupBy,
      subGroupBy,
      orderBy !== "sort_order"
    ).catch((err) => {
      setToast({
        title: "Error!",
        type: TOAST_TYPE.ERROR,
        message: err?.detail ?? "Failed to perform this action",
      });
    });
  };

  return handleOnDrop;
};
