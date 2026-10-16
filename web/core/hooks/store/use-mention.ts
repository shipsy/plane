"use client";

import { useRef, useEffect } from "react";
// plane editor
import { IMentionSuggestion } from "@plane/editor";
// plane types
import { IUser, IUserLite } from "@plane/types";
// helpers
import { getFileURL } from "@/helpers/file.helper";
// hooks
import { useMember } from "@/hooks/store/use-member";

// cap keeps the mention popup render small
const MENTION_SUGGESTION_LIMIT = 20;
// single characters are filtered locally; longer queries hit the server
const SERVER_SEARCH_MIN_CHARS = 2;
const SERVER_SEARCH_DEBOUNCE_MS = 300;

type Props = {
  workspaceSlug?: string;
  projectId?: string;
  members?: IUserLite[] | undefined;
  user?: IUser | undefined;
};

export const useMention = ({ workspaceSlug, projectId, members, user }: Props) => {
  const projectMembersRef = useRef<IUserLite[] | undefined>();
  const userRef = useRef<IUser | undefined>();
  // a newer keystroke supersedes a pending search; MentionList drops the
  // stale result, so the superseded promise just resolves empty
  const searchTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const pendingSearchRef = useRef<(members: IUserLite[]) => void>();

  const {
    getUserDetails,
    project: { searchProjectMembers },
  } = useMember();

  useEffect(() => {
    if (members) projectMembersRef.current = members;
    else {
      if (!workspaceSlug || !projectId) return;
      // load a capped member list for mention suggestions instead of the
      // full project member list
      searchProjectMembers(workspaceSlug.toString(), projectId.toString(), { per_page: MENTION_SUGGESTION_LIMIT });
    }
  }, [searchProjectMembers, members, projectId, workspaceSlug]);

  useEffect(() => {
    if (userRef) userRef.current = user;
  }, [user]);

  // drop a pending search when the editor unmounts
  useEffect(
    () => () => {
      clearTimeout(searchTimerRef.current);
      pendingSearchRef.current?.([]);
    },
    []
  );

  const waitForUserData = async () =>
    new Promise<IUser>((resolve) => {
      const checkData = () => {
        if (userRef.current) resolve(userRef.current);
        else setTimeout(checkData, 100);
      };
      checkData();
    });

  const mentionHighlights = async () => {
    if (user && userRef.current) {
      return [userRef.current.id];
    } else {
      const userData = await waitForUserData();
      return [userData.id];
    }
  };

  const toMembers = (userIds: string[]) =>
    userIds.map((userId) => getUserDetails(userId)).filter((member): member is IUserLite => !!member);

  // match every typed term like the server does, then rank names starting
  // with the query first and only then cap the list
  const filterAndRank = (list: IUserLite[], query: string) => {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0) return list.slice(0, MENTION_SUGGESTION_LIMIT);
    const prefixMatches: IUserLite[] = [];
    const otherMatches: IUserLite[] = [];
    list.forEach((member) => {
      const displayName = (member?.display_name ?? "").toLowerCase();
      const firstName = (member?.first_name ?? "").toLowerCase();
      const searchText = `${displayName} ${firstName} ${(member?.last_name ?? "").toLowerCase()}`;
      if (!terms.every((term) => searchText.includes(term))) return;
      if (displayName.startsWith(terms[0]) || firstName.startsWith(terms[0])) prefixMatches.push(member);
      else otherMatches.push(member);
    });
    return [...prefixMatches, ...otherMatches].slice(0, MENTION_SUGGESTION_LIMIT);
  };

  // the store may hold only a capped member list (e.g. outside the project
  // wrapper), so typed queries are searched on the server
  const searchMembers = (slug: string, memberProjectId: string, query: string) =>
    new Promise<IUserLite[]>((resolve) => {
      clearTimeout(searchTimerRef.current);
      pendingSearchRef.current?.([]);
      pendingSearchRef.current = resolve;
      searchTimerRef.current = setTimeout(() => {
        pendingSearchRef.current = undefined;
        searchProjectMembers(slug, memberProjectId, {
          search: query,
          per_page: MENTION_SUGGESTION_LIMIT,
        })
          // reorder the capped server page so prefix matches come first
          .then((userIds) => resolve(filterAndRank(toMembers(userIds), query)))
          .catch(() => resolve(filterAndRank(projectMembersRef.current ?? [], query)));
      }, SERVER_SEARCH_DEBOUNCE_MS);
    });

  const getMembers = async (query: string) => {
    const trimmedQuery = query.trim();
    const localMatches = filterAndRank(projectMembersRef.current ?? [], trimmedQuery);
    if (!workspaceSlug || !projectId) return localMatches;
    if (trimmedQuery.length >= SERVER_SEARCH_MIN_CHARS)
      return searchMembers(workspaceSlug.toString(), projectId.toString(), trimmedQuery);
    // a short query, or members are already loaded
    if (trimmedQuery || localMatches.length > 0) return localMatches;
    // nothing loaded yet, fetch the first page instead of polling the store
    const userIds = await searchProjectMembers(workspaceSlug.toString(), projectId.toString(), {
      per_page: MENTION_SUGGESTION_LIMIT,
    }).catch(() => [] as string[]);
    return toMembers(userIds);
  };

  const mentionSuggestions = async (query: string = ""): Promise<IMentionSuggestion[]> => {
    const membersList = await getMembers(query);
    return membersList.map((memberDetails) => ({
      entity_name: "user_mention",
      entity_identifier: `${memberDetails?.id}`,
      id: `${memberDetails?.id}`,
      type: "User",
      title: `${memberDetails?.display_name}`,
      subtitle: memberDetails?.email ?? "",
      avatar: getFileURL(memberDetails?.avatar_url) ?? "",
      redirect_uri: `/${workspaceSlug}/profile/${memberDetails?.id}`,
    }));
  };

  return {
    mentionSuggestions,
    mentionHighlights,
  };
};
