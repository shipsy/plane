"use client";

import { useCallback, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// types
import { ChevronDown, Download, Layers } from "lucide-react";
import { IIssueDisplayFilterOptions, IIssueDisplayProperties, IIssueFilterOptions } from "@plane/types";
// ui
import { useTranslation } from "@plane/i18n";
import { Breadcrumbs, Button, CustomMenu, Header } from "@plane/ui";
// components
import { BreadcrumbLink } from "@/components/common";
import { Exporter } from "@/components/exporter";
import { DisplayFiltersSelection, FiltersDropdown, FilterSelection } from "@/components/issues";
import { CreateUpdateWorkspaceViewModal } from "@/components/workspace";
// constants
import { EIssueFilterType, EIssuesStoreType, ISSUE_DISPLAY_FILTERS_BY_LAYOUT } from "@/constants/issue";
// helpers
import { isIssueFilterActive } from "@/helpers/filter.helper";
// hooks
import { useLabel, useMember, useIssues, useGlobalView, useUser } from "@/hooks/store";

export const GlobalIssuesHeader = observer(() => {
  const { t } = useTranslation();
  // states
  const [createViewModal, setCreateViewModal] = useState(false);
  const [exportProvider, setExportProvider] = useState<string | null>(null);
  // router
  const { workspaceSlug, globalViewId } = useParams();
  // store hooks
  const {
    issuesFilter: { filters, updateFilters },
  } = useIssues(EIssuesStoreType.GLOBAL);
  const { getViewDetailsById } = useGlobalView();
  const { data: currentUser } = useUser();
  const { workspaceLabels } = useLabel();
  const {
    workspace: { workspaceMemberIds },
  } = useMember();

  const issueFilters = globalViewId ? filters[globalViewId.toString()] : undefined;

  const viewDetails = getViewDetailsById(globalViewId.toString());

  const handleFiltersUpdate = useCallback(
    (key: keyof IIssueFilterOptions, value: string | string[]) => {
      if (!workspaceSlug || !globalViewId) return;
      const newValues = issueFilters?.filters?.[key] ?? [];

      if (Array.isArray(value)) {
        // this validation is majorly for the filter start_date, target_date custom
        value.forEach((val) => {
          if (!newValues.includes(val)) newValues.push(val);
          else newValues.splice(newValues.indexOf(val), 1);
        });
      } else {
        if (issueFilters?.filters?.[key]?.includes(value)) newValues.splice(newValues.indexOf(value), 1);
        else newValues.push(value);
      }

      updateFilters(
        workspaceSlug.toString(),
        undefined,
        EIssueFilterType.FILTERS,
        { [key]: newValues },
        globalViewId.toString()
      );
    },
    [workspaceSlug, issueFilters, updateFilters, globalViewId]
  );

  const handleDisplayFilters = useCallback(
    (updatedDisplayFilter: Partial<IIssueDisplayFilterOptions>) => {
      if (!workspaceSlug || !globalViewId) return;
      updateFilters(
        workspaceSlug.toString(),
        undefined,
        EIssueFilterType.DISPLAY_FILTERS,
        updatedDisplayFilter,
        globalViewId.toString()
      );
    },
    [workspaceSlug, updateFilters, globalViewId]
  );

  const handleDisplayProperties = useCallback(
    (property: Partial<IIssueDisplayProperties>) => {
      if (!workspaceSlug || !globalViewId) return;
      updateFilters(
        workspaceSlug.toString(),
        undefined,
        EIssueFilterType.DISPLAY_PROPERTIES,
        property as IIssueDisplayProperties,
        globalViewId.toString()
      );
    },
    [workspaceSlug, updateFilters, globalViewId]
  );

  const isLocked = viewDetails?.is_locked;

  return (
    <>
      <CreateUpdateWorkspaceViewModal isOpen={createViewModal} onClose={() => setCreateViewModal(false)} />
      <Header>
        <Header.LeftItem>
          <Breadcrumbs>
            <Breadcrumbs.BreadcrumbItem
              type="text"
              link={<BreadcrumbLink label={t("views")} icon={<Layers className="h-4 w-4 text-custom-text-300" />} />}
            />
          </Breadcrumbs>
        </Header.LeftItem>

        <Header.RightItem>
          {!isLocked ? (
            <>
              <FiltersDropdown
                title={t("filters")}
                placement="bottom-end"
                isFiltersApplied={isIssueFilterActive(issueFilters)}
              >
                <FilterSelection
                  layoutDisplayFiltersOptions={ISSUE_DISPLAY_FILTERS_BY_LAYOUT.my_issues.spreadsheet}
                  filters={issueFilters?.filters ?? {}}
                  handleFiltersUpdate={handleFiltersUpdate}
                  displayFilters={issueFilters?.displayFilters ?? {}}
                  handleDisplayFiltersUpdate={handleDisplayFilters}
                  labels={workspaceLabels ?? undefined}
                  memberIds={workspaceMemberIds ?? undefined}
                />
              </FiltersDropdown>
              <FiltersDropdown title={t("display")} placement="bottom-end">
                <DisplayFiltersSelection
                  layoutDisplayFiltersOptions={ISSUE_DISPLAY_FILTERS_BY_LAYOUT.my_issues.spreadsheet}
                  displayFilters={issueFilters?.displayFilters ?? {}}
                  handleDisplayFiltersUpdate={handleDisplayFilters}
                  displayProperties={issueFilters?.displayProperties ?? {}}
                  handleDisplayPropertiesUpdate={handleDisplayProperties}
                />
              </FiltersDropdown>
            </>
          ) : (
            <></>
          )}

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
            <CustomMenu.MenuItem onClick={() => setExportProvider("xlsx")}>Excel</CustomMenu.MenuItem>
            <CustomMenu.MenuItem onClick={() => setExportProvider("json")}>JSON</CustomMenu.MenuItem>
          </CustomMenu>

          <Button variant="primary" size="sm" onClick={() => setCreateViewModal(true)}>
          {t("add_view")}
          </Button>
        </Header.RightItem>
      </Header>
      {exportProvider && (
        <Exporter
          isOpen
          handleClose={() => setExportProvider(null)}
          data={null}
          user={currentUser || null}
          provider={exportProvider}
          mutateServices={() => {}}
        />
      )}
    </>
  );
});
