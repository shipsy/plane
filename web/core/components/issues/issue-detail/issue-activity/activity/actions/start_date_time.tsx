import { FC } from "react";
import { observer } from "mobx-react";
import { CalendarClock } from "lucide-react";
// hooks
import { renderFormattedDate, renderFormattedTime } from "@/helpers/date-time.helper";
import { useIssueDetail } from "@/hooks/store";
// components
import { IssueActivityBlockComponent, IssueLink } from "./";
// helpers
import { useTranslation } from "@plane/i18n";

type TIssueStartDateTimeActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssueStartDateTimeActivity: FC<TIssueStartDateTimeActivity> = observer((props) => {
  const { activityId, showIssue = true, ends } = props;
  const { t } = useTranslation();
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<CalendarClock size={14} className="text-custom-text-200" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {activity.new_value
          ? `${t("set_start_date_time_to")} `
          : `${t("removed_start_date_time")} `}
        {activity.new_value && (
          <span className="font-medium text-custom-text-100">
            {`${renderFormattedDate(activity.new_value)} ${renderFormattedTime(activity.new_value, "12-hour")}`}
          </span>
        )}
        {showIssue && (activity.new_value ? ` ${t("for")} ` : ` ${t("from")} `)}
        {showIssue && <IssueLink activityId={activityId} />}.
      </>
    </IssueActivityBlockComponent>
  );
});
