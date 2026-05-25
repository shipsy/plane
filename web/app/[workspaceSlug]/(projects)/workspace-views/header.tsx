"use client";

import { useCallback, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// types
import { Layers } from "lucide-react";
import { IIssueDisplayFilterOptions, IIssueDisplayProperties, IIssueFilterOptions, TIssue } from "@plane/types";
// services
import { WorkspaceService } from "@/services/workspace.service";
// ui
import { useTranslation } from "@plane/i18n";
import { Breadcrumbs, Button, Header } from "@plane/ui";
// components
import { BreadcrumbLink } from "@/components/common";
import { ALL_ISSUES } from "@plane/constants";
import { DisplayFiltersSelection, DownloadIssuesButton, FiltersDropdown, FilterSelection } from "@/components/issues";
import { CreateUpdateWorkspaceViewModal } from "@/components/workspace";
// constants
import { EIssueFilterType, EIssuesStoreType, ISSUE_DISPLAY_FILTERS_BY_LAYOUT } from "@/constants/issue";
// helpers
import { isIssueFilterActive } from "@/helpers/filter.helper";
// hooks
import { useLabel, useMember, useIssues, useGlobalView } from "@/hooks/store";

export const GlobalIssuesHeader = observer(() => {
  const { t } = useTranslation();
  // states
  const [createViewModal, setCreateViewModal] = useState(false);
  // router
  const { workspaceSlug, globalViewId } = useParams();
  // store hooks
  const {
    issuesFilter: { filters, updateFilters, getAppliedFilters },
    issues: { groupedIssueIds },
    issueMap,
  } = useIssues(EIssuesStoreType.GLOBAL);

  const slug = Array.isArray(workspaceSlug) ? workspaceSlug[0] : workspaceSlug;
  const viewId = Array.isArray(globalViewId) ? globalViewId[0] : globalViewId;

  // Paginate the workspace issues endpoint with the current global-view filters
  // so the CSV reflects the full filtered set rather than what's in memory.
  // Returns `hitHardCap = true` when we stopped at the page cap while the server
  // still had more results, so the UI can warn the user that the export is partial.
  const fetchAllGlobalIssues = useCallback(async (): Promise<{
    issues: TIssue[];
    hitHardCap: boolean;
  }> => {
    if (!slug || !viewId) return { issues: [], hitHardCap: false };
    const workspaceService = new WorkspaceService();
    const appliedFilters = (getAppliedFilters?.(viewId) as Record<string, any>) || {};
    const baseParams: Record<string, any> = { ...appliedFilters };
    delete baseParams.group_by;
    delete baseParams.sub_group_by;

    const PER_PAGE = 500;
    const HARD_CAP_PAGES = 50; // 25,000 issues max
    const all: TIssue[] = [];
    let cursor = `${PER_PAGE}:0:0`;
    let hitHardCap = false;
    for (let page = 0; page < HARD_CAP_PAGES; page++) {
      const response = await workspaceService.getViewIssues(slug, {
        ...baseParams,
        cursor,
        per_page: PER_PAGE,
      });
      const results = response?.results;
      if (Array.isArray(results)) all.push(...(results as TIssue[]));

      // Natural end: server has no more pages.
      if (!response?.next_page_results || !response?.next_cursor) break;

      // Last allowed iteration but server still has more → cap hit, flag it.
      if (page === HARD_CAP_PAGES - 1) {
        hitHardCap = true;
        break;
      }
      cursor = response.next_cursor;
    }
    return { issues: all, hitHardCap };
  }, [slug, viewId, getAppliedFilters]);
  const { getViewDetailsById } = useGlobalView();
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

          <DownloadIssuesButton
            issueIds={
              (globalViewId && groupedIssueIds && (groupedIssueIds as any)[ALL_ISSUES]) || []
            }
            issueMap={issueMap}
            displayProperties={issueFilters?.displayProperties ?? {}}
            fileName={`${viewDetails?.name || viewId || "issues"}`}
            fetchAllIssues={fetchAllGlobalIssues}
          />

          <Button variant="primary" size="sm" onClick={() => setCreateViewModal(true)}>
          {t("add_view")}
          </Button>
        </Header.RightItem>
      </Header>
    </>
  );
});
