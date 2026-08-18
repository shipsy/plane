"use client";

import { useEffect, useRef, useState } from "react";
import { Placement } from "@popperjs/core";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { createPortal } from "react-dom";
import { usePopper } from "react-popper";
import { Check, Search } from "lucide-react";
import { Combobox } from "@headlessui/react";
import { useTranslation } from "@plane/i18n";
// plane ui
import { Avatar } from "@plane/ui";
// helpers
import { cn } from "@/helpers/common.helper";
import { getFileURL } from "@/helpers/file.helper";
// hooks
import { useUser, useMember } from "@/hooks/store";
import { usePlatformOS } from "@/hooks/use-platform-os";

interface Props {
  className?: string;
  optionsClassName?: string;
  projectId?: string;
  referenceElement: HTMLButtonElement | null;
  placement: Placement | undefined;
  isOpen: boolean;
  value?: string | string[] | null;
}

// maximum number of options rendered in the dropdown at once
const OPTIONS_RENDER_LIMIT = 20;
// minimum characters before the query is searched on the server
const SERVER_SEARCH_MIN_CHARS = 3;
// debounce interval for server search
const SERVER_SEARCH_DEBOUNCE_MS = 300;

export const MemberOptions: React.FC<Props> = observer((props: Props) => {
  const { projectId, referenceElement, placement, isOpen, optionsClassName = "", value } = props;
  // states
  const [query, setQuery] = useState("");
  const [searchedUserIds, setSearchedUserIds] = useState<string[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [popperElement, setPopperElement] = useState<HTMLDivElement | null>(null);
  // refs
  const inputRef = useRef<HTMLInputElement | null>(null);
  // store hooks
  const { t } = useTranslation();
  const { workspaceSlug } = useParams();
  const {
    getUserDetails,
    project: { getProjectMemberIds, searchProjectMembers },
    workspace: { workspaceMemberIds },
  } = useMember();
  const { data: currentUser } = useUser();
  const { isMobile } = usePlatformOS();
  // popper-js init
  const { styles, attributes } = usePopper(referenceElement, popperElement, {
    placement: placement ?? "bottom-start",
    modifiers: [
      {
        name: "preventOverflow",
        options: {
          padding: 12,
        },
      },
    ],
  });

  useEffect(() => {
    if (isOpen) {
      onOpen();
      if (!isMobile) {
        inputRef.current && inputRef.current.focus();
      }
    }
  }, [isOpen, isMobile]);

  const memberIds = projectId ? getProjectMemberIds(projectId) : workspaceMemberIds;
  const onOpen = () => {
    if (!memberIds && workspaceSlug && projectId)
      searchProjectMembers(workspaceSlug.toString(), projectId, { per_page: OPTIONS_RENDER_LIMIT });
  };

  // server-side member search for project dropdowns, debounced and
  // triggered only once the query is long enough
  const trimmedQuery = query.trim();
  useEffect(() => {
    if (!workspaceSlug || !projectId || trimmedQuery.length < SERVER_SEARCH_MIN_CHARS) {
      setSearchedUserIds(null);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    let cancelled = false;
    const timer = setTimeout(() => {
      searchProjectMembers(workspaceSlug.toString(), projectId, {
        search: trimmedQuery,
        per_page: OPTIONS_RENDER_LIMIT,
      })
        .then((userIds) => {
          if (!cancelled) setSearchedUserIds(userIds);
        })
        .catch(() => {
          if (!cancelled) setSearchedUserIds(null);
        })
        .finally(() => {
          if (!cancelled) setIsSearching(false);
        });
    }, SERVER_SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [trimmedQuery, workspaceSlug, projectId, searchProjectMembers]);

  const searchInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (query !== "" && e.key === "Escape") {
      e.stopPropagation();
      setQuery("");
    }
  };

  const isServerSearchActive = !!projectId && searchedUserIds !== null;
  const baseIds = isServerSearchActive ? searchedUserIds : memberIds;

  // pin the currently selected member(s) to the top of the list
  const selectedIds = Array.isArray(value) ? value : value ? [value] : [];
  let optionIds = baseIds;
  if (baseIds) {
    if (isServerSearchActive) {
      optionIds = [...baseIds].sort(
        (a, b) => Number(selectedIds.includes(b)) - Number(selectedIds.includes(a))
      );
    } else {
      optionIds = [
        ...selectedIds.filter((userId) => getUserDetails(userId)),
        ...baseIds.filter((userId) => !selectedIds.includes(userId)),
      ];
    }
  }

  // filter at the id level and only build option objects for the rendered
  // slice, so a large member list never causes a heavy render
  const queryLowerCase = query.toLowerCase();
  const matchingIds =
    isServerSearchActive || query === ""
      ? optionIds
      : optionIds?.filter((userId) => {
          const userDetails = getUserDetails(userId);
          return `${userDetails?.display_name} ${userDetails?.first_name} ${userDetails?.last_name}`
            .toLowerCase()
            .includes(queryLowerCase);
        });

  const visibleOptions = matchingIds?.slice(0, OPTIONS_RENDER_LIMIT).map((userId) => {
    const userDetails = getUserDetails(userId);

    return {
      value: userId,
      content: (
        <div className="flex items-center gap-2">
          <Avatar name={userDetails?.display_name} src={getFileURL(userDetails?.avatar_url ?? "")} />
          <span className="flex-grow truncate">{currentUser?.id === userId ? t("you") : userDetails?.display_name}</span>
        </div>
      ),
    };
  });

  return createPortal(
    <Combobox.Options data-prevent-outside-click static>
      <div
        className={cn(
          "my-1 w-48 rounded border-[0.5px] border-custom-border-300 bg-custom-background-100 px-2 py-2.5 text-xs shadow-custom-shadow-rg focus:outline-none z-20",
          optionsClassName
        )}
        ref={setPopperElement}
        style={{
          ...styles.popper,
        }}
        {...attributes.popper}
      >
        <div className="flex items-center gap-1.5 rounded border border-custom-border-100 bg-custom-background-90 px-2">
          <Search className="h-3.5 w-3.5 text-custom-text-400" strokeWidth={1.5} />
          <Combobox.Input
            as="input"
            ref={inputRef}
            className="w-full bg-transparent py-1 text-xs text-custom-text-200 placeholder:text-custom-text-400 focus:outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("search")}
            displayValue={(assigned: any) => assigned?.name}
            onKeyDown={searchInputKeyDown}
          />
        </div>
        <div className="mt-2 max-h-48 space-y-1 overflow-y-scroll">
          {isSearching ? (
            <p className="px-1.5 py-1 italic text-custom-text-400">{t("loading")}</p>
          ) : visibleOptions ? (
            visibleOptions.length > 0 ? (
              visibleOptions.map((option) => (
                <Combobox.Option
                  key={option.value}
                  value={option.value}
                  className={({ active, selected }) =>
                    `flex w-full cursor-pointer select-none items-center justify-between gap-2 truncate rounded px-1 py-1.5 ${
                      active ? "bg-custom-background-80" : ""
                    } ${selected ? "text-custom-text-100" : "text-custom-text-200"}`
                  }
                >
                  {({ selected }) => (
                    <>
                      <span className="flex-grow truncate">{option.content}</span>
                      {selected && <Check className="h-3.5 w-3.5 flex-shrink-0" />}
                    </>
                  )}
                </Combobox.Option>
              ))
            ) : (
              <p className="px-1.5 py-1 italic text-custom-text-400">{t("no_matching_results")}</p>
            )
          ) : (
            <p className="px-1.5 py-1 italic text-custom-text-400">{t("loading")}</p>
          )}
        </div>
      </div>
    </Combobox.Options>,
    document.body
  );
});