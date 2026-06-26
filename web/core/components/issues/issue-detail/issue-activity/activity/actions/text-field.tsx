"use client";

import { FC } from "react";
import { observer } from "mobx-react";
import { SquarePen } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { useIssueDetail } from "@/hooks/store";
import { IssueActivityBlockComponent } from "./";

type TIssueTextFieldActivity = { activityId: string; ends: "top" | "bottom" | undefined };

export const IssueTextFieldActivity: FC<TIssueTextFieldActivity> = observer((props) => {
  const { activityId, ends } = props;
  const { t } = useTranslation();
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);
  if (!activity) return <></>;

  const fieldLabel = t(activity.field as string);

  return (
    <IssueActivityBlockComponent
      icon={<SquarePen size={14} className="text-custom-text-200" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {activity.old_value ? (
          <>
            {t("updated")} <span className="font-medium text-custom-text-100">{fieldLabel}</span>{" "}
            {t("from")} <span className="font-medium text-custom-text-100">{activity.old_value}</span>{" "}
            {t("to")} <span className="font-medium text-custom-text-100">{activity.new_value}</span>.
          </>
        ) : (
          <>
            {t("set")} <span className="font-medium text-custom-text-100">{fieldLabel}</span>{" "}
            {t("to")} <span className="font-medium text-custom-text-100">{activity.new_value}</span>.
          </>
        )}
      </>
    </IssueActivityBlockComponent>
  );
});
