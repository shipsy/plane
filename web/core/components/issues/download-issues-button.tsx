"use client";

import React from "react";
import { observer } from "mobx-react";
import { Download } from "lucide-react";
// types
import { IIssueDisplayProperties, TIssue, TIssueMap } from "@plane/types";
// ui
import { Button, setToast, TOAST_TYPE } from "@plane/ui";
// router + permissions store for discovering workspace-level custom fields
import { useParams } from "next/navigation";
import { useCycle, useLabel, useMember, useModule, useProject, useProjectState, useUserPermissions } from "@/hooks/store";
// Canonical column order used by the on-screen spreadsheet — reused here so the CSV matches it exactly.
import { SPREADSHEET_PROPERTY_LIST } from "@/constants/spreadsheet";

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

// Translates displayProperty keys to the underlying TIssue field name when they differ.
// Pure data — no inclusion logic, no per-column branches. Added only so the dynamic
// lookup actually finds the right field; Plane's schema names don't match every UI toggle.
const FIELD_ALIAS: Record<string, string> = {
  due_date: "target_date",
  created_on: "created_at",
  updated_on: "updated_at",
  estimate: "estimate_point",
  link: "link_count",
  labels: "label_ids",
  modules: "module_ids",
  assignee: "assignee_ids",
  state: "state_id",
  cycle: "cycle_id",
  issue_type: "type_id",
  sub_issue_count: "sub_issues_count",
};

// Pulls the value for a display-property key off an issue: alias → raw key →
// common suffix variants → custom_property_values. No property is hardcoded for inclusion.
const getIssueValueForKey = (issue: TIssue, key: string): any => {
  // 1. Custom property values: Array<{ [name]: value }>
  const cpv: Array<Record<string, any>> = (issue as any)?.custom_property_values ?? [];
  const found = cpv.find((item) => item && Object.prototype.hasOwnProperty.call(item, key));
  if (found && found[key] !== undefined && found[key] !== null && found[key] !== "") return found[key];

  // 2. Field lookup: aliased field first, then raw key, then common suffix variants.
  const aliased = FIELD_ALIAS[key];
  const variants = [
    ...(aliased ? [aliased] : []),
    key,
    `${key}_id`,
    `${key}_ids`,
    `${key}_count`,
    `${key}s_count`,
    `${key}_at`,
    `${key}_date`,
  ];
  for (const v of variants) {
    const val = (issue as any)?.[v];
    if (val !== undefined && val !== null && val !== "") return val;
  }

  // 3. The `key` toggle represents the "PROJ-123" ID column, which is derived from sequence_id.
  if (key === "key") {
    const seq = (issue as any)?.sequence_id;
    return seq !== undefined && seq !== null ? String(seq) : "";
  }

  return "";
};

export const DownloadIssuesButton: React.FC<Props> = observer((props) => {
  const { issueIds, issueMap, displayProperties, fileName = "issues" } = props;
  const { workspaceUserInfo } = useUserPermissions();
  const { workspaceSlug } = useParams();
  // Resolver stores — used to turn raw foreign-key IDs into human names. Keyed dynamically below.
  const { getStateById } = useProjectState();
  const { getLabelById } = useLabel();
  const { getUserDetails } = useMember();
  const { getModuleById } = useModule();
  const { getCycleById } = useCycle();
  const { getProjectIdentifierById } = useProject();

  // Resolver registry — maps a displayProperty key to a function that turns a raw value (typically
  // an ID or array of IDs) into a human-readable string. Keys that don't appear here fall back to
  // the dynamic stringifier. This is a value-translation table, not a column inclusion list.
  const RESOLVERS: Record<string, (val: any) => string> = {
    state: (v) => (typeof v === "string" ? getStateById(v)?.name ?? v : "") as string,
    assignee: (v) => {
      const ids = Array.isArray(v) ? v : v ? [v] : [];
      return ids
        .map((id: string) => getUserDetails(id)?.display_name || getUserDetails(id)?.email || id)
        .filter(Boolean)
        .join(", ");
    },
    labels: (v) => {
      const ids = Array.isArray(v) ? v : v ? [v] : [];
      return ids.map((id: string) => getLabelById(id)?.name || id).filter(Boolean).join(", ");
    },
    modules: (v) => {
      const ids = Array.isArray(v) ? v : v ? [v] : [];
      return ids.map((id: string) => getModuleById(id)?.name || id).filter(Boolean).join(", ");
    },
    cycle: (v) => (typeof v === "string" ? getCycleById(v)?.name ?? v : "") as string,
  };

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

    // Workspace-level custom field catalog (the spreadsheet appends these after the standard columns).
    const wsCustom =
      (workspaceUserInfo as any)?.[workspaceSlug?.toString() ?? ""]?.default_props?.display_properties
        ?.custom_properties || {};

    // Same predicate the spreadsheet uses: include the column only if displayProperties[key] is truthy.
    // (See header-column.tsx — `if (!displayProperties?.[property]) return null;`.) For custom fields
    // we additionally allow the toggle to live under displayProperties.custom_properties[key].
    const visited = new Set<string>();
    const pushColumn = (key: string) => {
      if (!key || visited.has(key) || key === "custom_properties") return;
      const on = dp[key] || dp?.custom_properties?.[key];
      if (!on) return;
      visited.add(key);
      const resolver = RESOLVERS[key];
      columns.push({
        header: humanize(key),
        get: (issue) => {
          // `key` is the "PROJ-123" ID column — needs project identifier + sequence_id.
          if (key === "key") {
            const ident = getProjectIdentifierById((issue as any).project_id);
            const seq = (issue as any)?.sequence_id;
            if (seq === undefined || seq === null) return "";
            return ident ? `${ident}-${seq}` : String(seq);
          }
          const raw = getIssueValueForKey(issue, key);
          return resolver ? resolver(raw) : stringify(raw);
        },
      });
    };

    // Standard columns first, in canonical spreadsheet order, then custom columns.
    SPREADSHEET_PROPERTY_LIST.forEach(pushColumn);
    // `key` (the PROJ-123 ID column) isn't in SPREADSHEET_PROPERTY_LIST but is a real toggle — try it too.
    pushColumn("key");
    // Custom properties: view-level toggles first, then workspace-level catalog. Do NOT use a
    // generic `Object.keys(dp)` catch-all — it sweeps in standard toggles like `issue_type` that
    // the on-screen spreadsheet intentionally doesn't render.
    Object.keys(dp.custom_properties || {}).forEach(pushColumn);
    Object.keys(wsCustom).forEach(pushColumn);

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
