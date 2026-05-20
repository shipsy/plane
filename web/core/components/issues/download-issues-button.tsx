"use client";

import React from "react";
import { observer } from "mobx-react";
import { Download } from "lucide-react";
// types
import { IIssueDisplayProperties, TIssue, TIssueMap } from "@plane/types";
// ui
import { Button, setToast, TOAST_TYPE } from "@plane/ui";
// hooks
import { useLabel, useMember, useProject, useProjectState } from "@/hooks/store";

type Props = {
  // Accepts either a flat list of issue IDs, or the grouped/sub-grouped issue map from the issues store.
  issueIds: string[] | Record<string, any> | undefined;
  issueMap: TIssueMap;
  displayProperties: IIssueDisplayProperties;
  fileName?: string;
};

const MAX_ROWS = 1000;

const flattenIds = (ids: any): string[] => {
  if (!ids) return [];
  if (Array.isArray(ids)) return ids as string[];
  const out = new Set<string>();
  Object.values(ids).forEach((v: any) => {
    if (Array.isArray(v)) v.forEach((id) => out.add(id));
    else if (v && typeof v === "object") {
      Object.values(v).forEach((arr: any) => {
        if (Array.isArray(arr)) arr.forEach((id) => out.add(id));
      });
    }
  });
  return Array.from(out);
};

const csvEscape = (val: any): string => {
  if (val === null || val === undefined) return "";
  const str = String(val);
  if (/[",\n\r]/.test(str)) return `"${str.replace(/"/g, '""')}"`;
  return str;
};

const formatDate = (val: string | null | undefined) => (val ? new Date(val).toISOString().split("T")[0] : "");

export const DownloadIssuesButton: React.FC<Props> = observer((props) => {
  const { issueIds, issueMap, displayProperties, fileName = "issues" } = props;
  // store hooks
  const { getStateById } = useProjectState();
  const { getLabelById } = useLabel();
  const {
    getUserDetails,
  } = useMember();
  const { getProjectIdentifierById, getProjectById } = useProject();

  const handleDownload = () => {
    const flatIds = flattenIds(issueIds);
    const allIssues: TIssue[] = flatIds.map((id) => issueMap?.[id]).filter(Boolean) as TIssue[];

    if (allIssues.length === 0) {
      setToast({ type: TOAST_TYPE.WARNING, title: "Nothing to download", message: "No issues are visible on screen." });
      return;
    }

    const truncated = allIssues.length > MAX_ROWS;
    const issues = truncated ? allIssues.slice(0, MAX_ROWS) : allIssues;

    const dp = displayProperties || {};

    const columns: { header: string; get: (issue: TIssue) => string }[] = [];

    if (dp.key !== false)
      columns.push({
        header: "ID",
        get: (i) => {
          const ident = getProjectIdentifierById(i.project_id);
          return ident ? `${ident}-${i.sequence_id}` : `${i.sequence_id ?? ""}`;
        },
      });

    columns.push({ header: "Title", get: (i) => i.name ?? "" });

    columns.push({ header: "Project", get: (i) => getProjectById(i.project_id)?.name ?? "" });

    if (dp.state !== false)
      columns.push({ header: "State", get: (i) => getStateById(i.state_id)?.name ?? "" });

    if (dp.priority !== false) columns.push({ header: "Priority", get: (i) => i.priority ?? "" });

    if (dp.assignee !== false)
      columns.push({
        header: "Assignees",
        get: (i) =>
          (i.assignee_ids ?? [])
            .map((uid) => getUserDetails(uid)?.display_name || getUserDetails(uid)?.email || "")
            .filter(Boolean)
            .join(", "),
      });

    if (dp.labels !== false)
      columns.push({
        header: "Labels",
        get: (i) =>
          (i.label_ids ?? [])
            .map((lid) => getLabelById(lid)?.name || "")
            .filter(Boolean)
            .join(", "),
      });

    if (dp.start_date !== false) columns.push({ header: "Start Date", get: (i) => formatDate(i.start_date) });
    if (dp.due_date !== false) columns.push({ header: "Due Date", get: (i) => formatDate(i.target_date) });

    if (dp.estimate) columns.push({ header: "Estimate", get: (i) => i.estimate_point ?? "" });
    if (dp.sub_issue_count) columns.push({ header: "Sub-Issues", get: (i) => String(i.sub_issues_count ?? 0) });
    if (dp.attachment_count) columns.push({ header: "Attachments", get: (i) => String(i.attachment_count ?? 0) });
    if (dp.link) columns.push({ header: "Links", get: (i) => String(i.link_count ?? 0) });
    if (dp.created_on) columns.push({ header: "Created On", get: (i) => formatDate(i.created_at) });
    if (dp.updated_on) columns.push({ header: "Updated On", get: (i) => formatDate(i.updated_at) });

    const lines: string[] = [];
    lines.push(columns.map((c) => csvEscape(c.header)).join(","));
    for (const issue of issues) {
      lines.push(columns.map((c) => csvEscape(c.get(issue))).join(","));
    }

    const csv = "﻿" + lines.join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    link.href = url;
    link.download = `${fileName}-${ts}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setToast({
      type: truncated ? TOAST_TYPE.WARNING : TOAST_TYPE.SUCCESS,
      title: truncated ? "Download truncated" : "Download started",
      message: truncated
        ? `Exported the first ${MAX_ROWS} of ${allIssues.length} issues. Apply filters to narrow the list.`
        : `Exported ${issues.length} issue${issues.length === 1 ? "" : "s"} to CSV.`,
    });
  };

  return (
    <Button variant="neutral-primary" size="sm" prependIcon={<Download className="h-3.5 w-3.5" />} onClick={handleDownload}>
      Download
    </Button>
  );
});
