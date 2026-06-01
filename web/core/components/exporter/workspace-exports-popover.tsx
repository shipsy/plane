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
// hooks
import { useIssues, useUser } from "@/hooks/store";

export const WorkspaceExportsPopover = observer(() => {
  const { data: currentUser } = useUser();
  const { globalViewId } = useParams();
  const { issuesFilter } = useIssues(EIssuesStoreType.GLOBAL);
  const [exportProvider, setExportProvider] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  // Mirror the same query params the issues list call sends so the export
  // server-side queryset matches what the user sees on the page.
  const filterParams = globalViewId
    ? (issuesFilter.getAppliedFilters?.(globalViewId.toString()) as Record<string, any> | undefined)
    : undefined;

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
          mutateServices={() => {}}
          filterParams={filterParams}
        />
      )}

      <ExportHistory isOpen={historyOpen} handleClose={() => setHistoryOpen(false)} />
    </>
  );
});
