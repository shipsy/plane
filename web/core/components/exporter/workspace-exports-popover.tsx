"use client";

import React, { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { ChevronDown, Download, History } from "lucide-react";
// ui
import { CustomMenu } from "@plane/ui";
// components
import { Exporter } from "./export-modal";
import { ExportHistory } from "./export-history";
// constants
import { EIssuesStoreType } from "@/constants/issue";
import { SPREADSHEET_PROPERTY_LIST } from "@/constants/spreadsheet";
// hooks
import { useIssues, useUser, useUserPermissions } from "@/hooks/store";
// plane web helpers
import { shouldRenderDisplayProperty } from "@/plane-web/helpers/issue-filter.helper";
import { EUserPermissions, EUserPermissionsLevel } from "@/plane-web/constants/user-permissions";

type Props = {
  // Which issue store the current page renders from; filters/columns are read
  // from it so the export matches the page. Defaults to the workspace-level
  // global store.
  storeType?: EIssuesStoreType.GLOBAL | EIssuesStoreType.PROJECT | EIssuesStoreType.PROJECT_VIEW;
  // The id the store keys its filters by: globalViewId (default), projectId
  // (project issues page) or viewId (project view page).
  entityId?: string;
  // When set, the export modal opens pre-scoped to this project.
  projectId?: string;
};

export const WorkspaceExportsPopover = observer((props: Props) => {
  const { storeType = EIssuesStoreType.GLOBAL, entityId, projectId } = props;
  const { data: currentUser } = useUser();
  const { globalViewId, workspaceSlug } = useParams();
  const { issuesFilter } = useIssues(storeType);
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const [exportProvider, setExportProvider] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  // Mirror the export endpoint's permission rule (workspace ADMIN/MEMBER,
  // see ExportIssuesEndpoint) — workspace guests can reach project pages via
  // project membership, and showing them the button only leads to a 403.
  const canExport = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.WORKSPACE
  );

  const filterKeyId = entityId ?? globalViewId?.toString();

  // Mirror the same query params the issues list call sends so the export
  // server-side queryset matches what the user sees on the page.
  const appliedFilters = filterKeyId ? issuesFilter.getAppliedFilters(filterKeyId) : undefined;

  // Forward the view's displayProperties so the CSV only contains the
  // columns the user has toggled on.
  const displayProperties = filterKeyId
    ? (issuesFilter.getIssueFilters(filterKeyId)?.displayProperties as Record<string, boolean> | undefined)
    : undefined;
  // Custom property columns in the same order the spreadsheet view renders
  // them (workspaceUserInfo custom_properties key order — see
  // spreadsheet-view.tsx), so the CSV column order matches the page.
  const customPropertyKeys = Object.keys(
    workspaceUserInfo[workspaceSlug?.toString() ?? ""]?.default_props?.display_properties?.custom_properties || {}
  );
  // Preserve the visible column order: standard columns follow
  // SPREADSHEET_PROPERTY_LIST, then custom properties in on-screen order,
  // then any remaining enabled keys (e.g. key) the server resolves by its
  // own registry order.
  const enabledDisplayProperties = displayProperties
    ? [
        ...SPREADSHEET_PROPERTY_LIST.filter((key) => !!displayProperties[key]),
        ...customPropertyKeys.filter((key) => !!displayProperties[key]),
        // Stored displayProperties can carry keys whose toggle is no longer
        // shown (e.g. issue_type, hidden since the picker gates on
        // shouldRenderDisplayProperty). Those never render on the page, so
        // apply the same gate here to keep them out of the CSV.
        ...Object.keys(displayProperties).filter(
          (key) =>
            !!displayProperties[key] &&
            !SPREADSHEET_PROPERTY_LIST.includes(key as never) &&
            !customPropertyKeys.includes(key) &&
            shouldRenderDisplayProperty({
              workspaceSlug: workspaceSlug?.toString() ?? "",
              projectId,
              key: key as never,
            })
        ),
      ].join(",")
    : undefined;

  const filterParams = {
    ...(appliedFilters ?? {}),
    ...(enabledDisplayProperties ? { display_properties: enabledDisplayProperties } : {}),
  };

  if (!canExport) return null;

  return (
    <>
      <CustomMenu
        customButton={
          <div className="flex items-center gap-1.5 rounded border border-custom-border-200 bg-custom-background-100 px-2 py-1 text-xs font-medium hover:bg-custom-background-80">
            <Download className="h-3 w-3" />
            <span>Download</span>
            <ChevronDown className="h-3 w-3" />
          </div>
        }
        placement="bottom-end"
        closeOnSelect
      >
        <CustomMenu.MenuItem onClick={() => setExportProvider("csv")}>CSV</CustomMenu.MenuItem>
        <CustomMenu.MenuItem onClick={() => setHistoryOpen(true)}>
          <span className="flex items-center gap-2">
            <History className="h-3 w-3" />
            View export history
          </span>
        </CustomMenu.MenuItem>
      </CustomMenu>

      {exportProvider && (
        <Exporter
          isOpen
          handleClose={() => setExportProvider(null)}
          data={null}
          user={currentUser || null}
          provider={exportProvider}
          mutateServices={
            // no-op: ExportHistory manages its own refresh via SWR
            () => {}
          }
          filterParams={filterParams}
          initialProjectIds={projectId ? [projectId] : undefined}
        />
      )}

      <ExportHistory isOpen={historyOpen} handleClose={() => setHistoryOpen(false)} />
    </>
  );
});
