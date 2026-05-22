import React from "react";
import { observer } from "mobx-react";
import { TIssue } from "@plane/types";
import { Row, Tooltip } from "@plane/ui";
import { renderFormattedDate, renderFormattedTime } from "@/helpers/date-time.helper";

type Props = {
  issue: TIssue;
  property: string;
};

export const SpreadsheetDateTimePropertyColumn: React.FC<Props> = observer((props) => {
  const { issue, property } = props;
  const value = issue && property ? (issue as any)[property] : null;
  const formatted = value ? `${renderFormattedDate(value)} ${renderFormattedTime(value)}` : "N/A";

  return (
    <Tooltip tooltipContent={formatted}>
      <Row className="h-11 truncate border-b-[0.5px] border-custom-border-200 pt-[1.25em] text-xs hover:bg-custom-background-80">
        {formatted}
      </Row>
    </Tooltip>
  );
});
