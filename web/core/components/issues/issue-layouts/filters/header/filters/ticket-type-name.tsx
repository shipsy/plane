"use client";

import React, { useMemo, useState } from "react";
import sortBy from "lodash/sortBy";
import { observer } from "mobx-react";
import { IIssueLabel } from "@plane/types";
import { useTranslation } from "@plane/i18n";
import { Loader } from "@plane/ui";
import { FilterHeader, FilterOption } from "@/components/issues";

const TicketTypeIcon = ({ color }: { color: string }) => (
  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
);

type Props = {
  appliedFilters: string[] | null;
  handleUpdate: (val: string) => void;
  ticketTypes: IIssueLabel[] | undefined;
  searchQuery: string;
};

export const FilterTicketTypeName: React.FC<Props> = observer((props) => {
  const { appliedFilters, handleUpdate, ticketTypes, searchQuery } = props;
  const { t } = useTranslation();

  const [itemsToRender, setItemsToRender] = useState(5);
  const [previewEnabled, setPreviewEnabled] = useState(true);

  const appliedFiltersCount = appliedFilters?.length ?? 0;

  const sortedOptions = useMemo(() => {
    const filteredOptions = (ticketTypes || []).filter((item) =>
      item.name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return sortBy(filteredOptions, [
      (item) => !(appliedFilters ?? []).includes(item.id),
      (item) => item.name.toLowerCase(),
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, ticketTypes]);

  const handleViewToggle = () => {
    if (!sortedOptions) return;

    if (itemsToRender === sortedOptions.length) setItemsToRender(5);
    else setItemsToRender(sortedOptions.length);
  };

  return (
    <>
      <FilterHeader
        title={`Ticket type name${appliedFiltersCount > 0 ? ` (${appliedFiltersCount})` : ""}`}
        isPreviewEnabled={previewEnabled}
        handleIsPreviewEnabled={() => setPreviewEnabled(!previewEnabled)}
      />
      {previewEnabled && (
        <div>
          {sortedOptions ? (
            sortedOptions.length > 0 ? (
              <>
                {sortedOptions.slice(0, itemsToRender).map((item) => (
                  <FilterOption
                    key={item?.id}
                    isChecked={appliedFilters?.includes(item?.id) ? true : false}
                    onClick={() => handleUpdate(item?.id)}
                    icon={<TicketTypeIcon color={item.color} />}
                    title={item.name}
                  />
                ))}
                {sortedOptions.length > 5 && (
                  <button
                    type="button"
                    className="ml-8 text-xs font-medium text-custom-primary-100"
                    onClick={handleViewToggle}
                  >
                    {itemsToRender === sortedOptions.length ? "View less" : "View all"}
                  </button>
                )}
              </>
            ) : (
              <p className="text-xs italic text-custom-text-400">{t("no_matches_found")}</p>
            )
          ) : (
            <Loader className="space-y-2">
              <Loader.Item height="20px" />
              <Loader.Item height="20px" />
              <Loader.Item height="20px" />
            </Loader>
          )}
        </div>
      )}
    </>
  );
});
