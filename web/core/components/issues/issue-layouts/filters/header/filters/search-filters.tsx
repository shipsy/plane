"use client";

import React, { useEffect, useState } from "react";
// import sortBy from "lodash/sortBy";
import { observer } from "mobx-react";
import useDebounce from "@/hooks/use-debounce";
// import { useParams } from "next/navigation";
// import { WorkspaceService } from "@/services/workspace.service";
// import { API_BASE_URL } from "@/helpers/common.helper";
import { usePlatformOS } from "@/hooks/use-platform-os";
import { Search, X } from "lucide-react";
// import { Loader, StateGroupIcon } from "@plane/ui";
import { FilterHeader, FilterOption } from "@/components/issues";

// type Props = {
//     appliedFilters: string[] | null;
//     handleUpdate: (val: string) => void;
//     searchQuery: string;
// };

export const FilterSearch: React.FC<Props> = observer(({groupKey, handleSectionSearch}) => {
    const { isMobile } = usePlatformOS();
    // const { workspaceSlug } = useParams();
    // const workspaceService = new WorkspaceService(API_BASE_URL);
    // const { appliedFilters, handleUpdate, searchQuery } = props;
    const [filtersSearchQuery, setFiltersSearchQuery] = useState("");

    // const debouncedSearchQuery = useDebounce(filtersSearchQuery, 500);

    // useEffect(() => {
    //     if (debouncedSearchQuery.length >= 3) {
    //         handleSectionSearch(groupKey, debouncedSearchQuery);
    //     }
    // }, [debouncedSearchQuery, groupKey, handleSectionSearch]);

    const handleSearch = (e) => {
        handleSectionSearch(groupKey, e.target.value);
        setFiltersSearchQuery(e.target.value);
    };

    return (
        <div className="bg-custom-background-100 pt-2">
            <div className="flex items-center gap-1.5 rounded border-[0.5px] border-custom-border-200 bg-custom-background-90 px-1.5 py-1 text-xs">
                <Search className="text-custom-text-400" size={12} strokeWidth={2} />
                <input
                    type="text"
                    className="w-full bg-custom-background-90 outline-none placeholder:text-custom-text-400"
                    placeholder="Search"
                    value={filtersSearchQuery}
                    onChange={(e) => handleSearch(e)}
                    autoFocus={!isMobile}
                />
            </div>
        </div>
    );
});
