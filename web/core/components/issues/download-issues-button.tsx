"use client";

import React from "react";
import { observer } from "mobx-react";
import { Download } from "lucide-react";
// types
import { IIssueDisplayProperties, TIssue, TIssueMap } from "@plane/types";
// ui
import { Button, setToast, TOAST_TYPE } from "@plane/ui";

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

const humanize = (key: string) => key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const stringify = (val: any): string => {
  if (val === null || val === undefined) return "";
  if (Array.isArray(val)) return val.filter((v) => v !== null && v !== undefined && v !== "").map(stringify).join(", ");
  if (typeof val === "object") {
    // ISO-ish date detection
    if (val instanceof Date) return val.toISOString();
    try {
      return JSON.stringify(val);
    } catch {
      return "";
    }
  }
  return String(val);
};

// Pulls the value for a display-property key off an issue, trying the common shapes
// Plane uses without enumerating any specific property name.
const getIssueValueForKey = (issue: TIssue, key: string): any => {
  // 1. custom_property_values: Array<{ [name]: value }>
  const cpv: Array<Record<string, any>> = (issue as any)?.custom_property_values ?? [];
  const found = cpv.find((item) => item && Object.prototype.hasOwnProperty.call(item, key));
  if (found && found[key] !== undefined && found[key] !== null && found[key] !== "") return found[key];

  // 2. Direct field on the issue, then common variants used across the schema.
  const variants = [key, `${key}_id`, `${key}_ids`, `${key}_count`, `${key}s_count`, `${key}_at`, `${key}_date`];
  for (const v of variants) {
    const val = (issue as any)?.[v];
    if (val !== undefined && val !== null && val !== "") return val;
  }
  return "";
};

export const DownloadIssuesButton: React.FC<Props> = observer((props) => {
  const { issueIds, issueMap, displayProperties, fileName = "issues" } = props;

  const handleDownload = () => {
    const flatIds = flattenIds(issueIds);
    const allIssues: TIssue[] = flatIds.map((id) => issueMap?.[id]).filter(Boolean) as TIssue[];

    if (allIssues.length === 0) {
      setToast({ type: TOAST_TYPE.WARNING, title: "Nothing to download", message: "No issues are visible on screen." });
      return;
    }

    const truncated = allIssues.length > MAX_ROWS;
    const issues = truncated ? allIssues.slice(0, MAX_ROWS) : allIssues;

    const dp: Record<string, any> = (displayProperties as any) || {};

    // Title is the only fixed column — it's the leftmost "Issues" cell and never appears in displayProperties.
    const columns: { header: string; get: (issue: TIssue) => string }[] = [
      { header: "Title", get: (i) => i.name ?? "" },
    ];

    // Everything else is driven entirely by what's toggled ON in displayProperties.
    // Insertion order of the source object becomes the column order in the CSV.
    const visited = new Set<string>();
    const pushColumn = (key: string) => {
      if (!key || visited.has(key) || key === "custom_properties") return;
      const directOn = dp[key];
      const nestedOn = dp?.custom_properties?.[key];
      // A column is shown unless either toggle is explicitly false.
      if (directOn === false || nestedOn === false) return;
      // If the key is absent from both toggle sources, skip it.
      if (directOn === undefined && nestedOn === undefined) return;
      visited.add(key);
      columns.push({
        header: humanize(key),
        get: (issue) => stringify(getIssueValueForKey(issue, key)),
      });
    };
    Object.keys(dp).forEach(pushColumn);
    Object.keys(dp.custom_properties || {}).forEach(pushColumn);

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
    <Button
      variant="neutral-primary"
      size="sm"
      prependIcon={<Download className="h-3.5 w-3.5" />}
      onClick={handleDownload}
    >
      Download
    </Button>
  );
});
