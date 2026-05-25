"use client";

import { useCallback, useState } from "react";
import { observer } from "mobx-react";
// types
import { IIssueDisplayFilterOptions, IIssueDisplayProperties, IIssueFilterOptions, TIssue } from "@plane/types";
// services
import { IssueService } from "@/services/issue/issue.service";
// ui
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/ui";

import { DisplayFiltersSelection, DownloadIssuesButton, FiltersDropdown, FilterSelection, LayoutSelection } from "@/components/issues";
// constants
import {
  EIssueFilterType,
  EIssuesStoreType,
  EIssueLayoutTypes,
  ISSUE_DISPLAY_FILTERS_BY_LAYOUT,
} from "@/constants/issue";
// helpers
import { isIssueFilterActive } from "@/helpers/filter.helper";
// hooks
import { useLabel, useProjectState, useMember, useIssues } from "@/hooks/store";
// plane web types
import { TProject } from "@/plane-web/types";
// local components
import { ProjectAnalyticsModal } from "../analytics";

type Props = {
  currentProjectDetails: TProject | undefined;
  projectId: string;
  workspaceSlug: string;
  canUserCreateIssue: boolean | undefined;
};
const HeaderFilters = observer(({ currentProjectDetails, projectId, workspaceSlug, canUserCreateIssue }: Props) => {
  const { t } = useTranslation();
  // states
  const [analyticsModal, setAnalyticsModal] = useState(false);
  // store hooks
  const {
    project: { projectMemberIds },
  } = useMember();
  const {
    issuesFilter,
    issues: { groupedIssueIds },
    issueMap,
  } = useIssues(EIssuesStoreType.PROJECT);
  const { issueFilters, updateFilters } = issuesFilter;

  // Lazily build a fetcher that walks the issue list endpoint (one page at a time,
  // ungrouped) with the current filters applied so the CSV reflects the full
  // filtered set, not just what the on-screen layout has paginated in.
  // Note: call `getAppliedFilters` off `issuesFilter` (not destructured) — it's a
  // regular class method that uses `this`, so destructuring breaks the binding.
  const fetchAllProjectIssues = useCallback(async (): Promise<TIssue[]> => {
    if (!workspaceSlug || !projectId) return [];
    const issueService = new IssueService();
    const appliedFilters = (issuesFilter.getAppliedFilters?.(projectId) as Record<string, any>) || {};
    const baseParams: Record<string, any> = { ...appliedFilters };
    // Force a flat (ungrouped) response and drop any layout-specific filters
    // so we get every matching issue, not just the current group/page.
    delete baseParams.group_by;
    delete baseParams.sub_group_by;

    const PER_PAGE = 500;
    const HARD_CAP_PAGES = 50; // safety net — 25k issues
    const all: TIssue[] = [];
    let cursor = `${PER_PAGE}:0:0`;
    for (let page = 0; page < HARD_CAP_PAGES; page++) {
      const response = await issueService.getIssuesFromServer(workspaceSlug, projectId, {
        ...baseParams,
        cursor,
        per_page: PER_PAGE,
      });
      const results = response?.results;
      if (Array.isArray(results)) all.push(...(results as TIssue[]));
      if (!response?.next_page_results || !response?.next_cursor) break;
      cursor = response.next_cursor;
    }
    return all;
  }, [workspaceSlug, projectId, issuesFilter]);

  const { projectStates } = useProjectState();
  const { projectLabels } = useLabel();
  const activeLayout = issueFilters?.displayFilters?.layout;

  const handleFiltersUpdate = useCallback(
    (key: keyof IIssueFilterOptions, value: string | string[]) => {
      if (!workspaceSlug || !projectId) return;
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

      updateFilters(workspaceSlug, projectId, EIssueFilterType.FILTERS, { [key]: newValues });
    },
    [workspaceSlug, projectId, issueFilters, updateFilters]
  );
  const handleLayoutChange = useCallback(
    (layout: EIssueLayoutTypes) => {
      if (!workspaceSlug || !projectId) return;
      updateFilters(workspaceSlug, projectId, EIssueFilterType.DISPLAY_FILTERS, { layout: layout });
    },
    [workspaceSlug, projectId, updateFilters]
  );

  const handleDisplayFilters = useCallback(
    (updatedDisplayFilter: Partial<IIssueDisplayFilterOptions>) => {
      if (!workspaceSlug || !projectId) return;
      updateFilters(workspaceSlug, projectId, EIssueFilterType.DISPLAY_FILTERS, updatedDisplayFilter);
    },
    [workspaceSlug, projectId, updateFilters]
  );

  const handleDisplayProperties = useCallback(
    (property: Partial<IIssueDisplayProperties>) => {
      if (!workspaceSlug || !projectId) return;
      updateFilters(workspaceSlug, projectId, EIssueFilterType.DISPLAY_PROPERTIES, property as IIssueDisplayProperties);
    },
    [workspaceSlug, projectId, updateFilters]
  );

  return (
    <>
      <ProjectAnalyticsModal
        isOpen={analyticsModal}
        onClose={() => setAnalyticsModal(false)}
        projectDetails={currentProjectDetails ?? undefined}
      />
      <LayoutSelection
        layouts={[
          EIssueLayoutTypes.LIST,
          EIssueLayoutTypes.KANBAN,
          EIssueLayoutTypes.CALENDAR,
          EIssueLayoutTypes.SPREADSHEET,
          EIssueLayoutTypes.GANTT,
        ]}
        onChange={(layout) => handleLayoutChange(layout)}
        selectedLayout={activeLayout}
      />
      <FiltersDropdown title={t("filters")} placement="bottom-end" isFiltersApplied={isIssueFilterActive(issueFilters)}>
        <FilterSelection
          filters={issueFilters?.filters ?? {}}
          handleFiltersUpdate={handleFiltersUpdate}
          displayFilters={issueFilters?.displayFilters ?? {}}
          handleDisplayFiltersUpdate={handleDisplayFilters}
          layoutDisplayFiltersOptions={activeLayout ? ISSUE_DISPLAY_FILTERS_BY_LAYOUT.issues[activeLayout] : undefined}
          labels={projectLabels}
          memberIds={projectMemberIds ?? undefined}
          states={projectStates}
          cycleViewDisabled={!currentProjectDetails?.cycle_view}
          moduleViewDisabled={!currentProjectDetails?.module_view}
        />
      </FiltersDropdown>
      <FiltersDropdown title={t("display")} placement="bottom-end">
        <DisplayFiltersSelection
          layoutDisplayFiltersOptions={activeLayout ? ISSUE_DISPLAY_FILTERS_BY_LAYOUT.issues[activeLayout] : undefined}
          displayFilters={issueFilters?.displayFilters ?? {}}
          handleDisplayFiltersUpdate={handleDisplayFilters}
          displayProperties={issueFilters?.displayProperties ?? {}}
          handleDisplayPropertiesUpdate={handleDisplayProperties}
          cycleViewDisabled={!currentProjectDetails?.cycle_view}
          moduleViewDisabled={!currentProjectDetails?.module_view}
        />
      </FiltersDropdown>
      <DownloadIssuesButton
        issueIds={(groupedIssueIds as any) ?? []}
        issueMap={issueMap}
        displayProperties={issueFilters?.displayProperties ?? {}}
        fileName={currentProjectDetails?.identifier ? `${currentProjectDetails.identifier}-issues` : "issues"}
        fetchAllIssues={fetchAllProjectIssues}
      />
      {canUserCreateIssue ? (
        <Button className="hidden md:block" onClick={() => setAnalyticsModal(true)} variant="neutral-primary" size="sm">
          {t("analytics")}
        </Button>
      ) : (
        <></>
      )}
    </>
  );
});

export default HeaderFilters;
