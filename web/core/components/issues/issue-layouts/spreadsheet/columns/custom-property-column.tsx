import React from "react";
import { observer } from "mobx-react";
import { TIssue } from "@plane/types";

interface Props {
  issue: TIssue;
  property: string;
  disableUserActions: boolean;
  onClose: () => void;
  onChange: (issue: TIssue, data: Partial<TIssue>, updates: any) => void;
}

export const SpreadsheetCustomPropertyColumn: React.FC<Props> = observer((props) => {
  const { issue, property, disableUserActions } = props;
  
  const customPropertyValue = issue.custom_properties?.find(
    (prop) => Object.keys(prop)[0] === property
  )?.[property];

  return (
    <div className="h-11 pl-2 text-sm w-full">
      <div className="flex h-full w-full items-center justify-start overflow-hidden">
        {customPropertyValue && (
          <span className="truncate">
            {customPropertyValue.toString()}
          </span>
        )}
      </div>
    </div>
  );
});
