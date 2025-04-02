import React from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// types
import { IIssueDisplayProperties } from "@plane/types";
// constants
import { ISSUE_DISPLAY_PROPERTIES } from "@/constants/issue";
// plane web helpers
import { shouldRenderDisplayProperty } from "@/plane-web/helpers/issue-filter.helper";
// components
import { FilterHeader } from "../helpers/filter-header";
import { issueCustomPropertyService } from "@/services/issue/custom-property.service";

type Props = {
  displayProperties: IIssueDisplayProperties;
  displayPropertiesToRender: (keyof IIssueDisplayProperties)[];
  handleUpdate: (updatedDisplayProperties: Partial<IIssueDisplayProperties>) => void;
  cycleViewDisabled?: boolean;
  moduleViewDisabled?: boolean;
};

export const FilterDisplayProperties: React.FC<Props> = observer((props) => {
  const {
    displayProperties,
    displayPropertiesToRender,
    handleUpdate,
    cycleViewDisabled = false,
    moduleViewDisabled = false,
  } = props;
  // router
  const { workspaceSlug, projectId: routerProjectId } = useParams();
  // states
  const [previewEnabled, setPreviewEnabled] = React.useState(true);
  const [customProperties, setCustomProperties] = React.useState<{ id: string; property_key: string; name: string }[]>([]);
  // derived values
  const projectId = !!routerProjectId ? routerProjectId?.toString() : undefined;

  React.useEffect(() => {
    if (workspaceSlug && projectId) {
      issueCustomPropertyService
        .getIssueTypeProperties(workspaceSlug.toString(), projectId)
        .then((data) => {
          setCustomProperties(data || []);
        })
        .catch((error) => {
          console.error("Error fetching custom properties:", error);
        });
    }
  }, [workspaceSlug, projectId]);

  const dynamicDisplayProperties = React.useMemo(() => {
    const customPropertyItems = customProperties.map((prop) => ({
      key: prop.property_key as keyof IIssueDisplayProperties,
      title: prop.name,
    }));
    
    return [...ISSUE_DISPLAY_PROPERTIES, ...customPropertyItems];
  }, [ISSUE_DISPLAY_PROPERTIES, customProperties]);

  // Filter out "cycle" and "module" keys if cycleViewDisabled or moduleViewDisabled is true
  // Also filter out display properties that should not be rendered
  const filteredDisplayProperties = dynamicDisplayProperties.filter((property) => {
    if (!displayPropertiesToRender.includes(property.key)) return false;
    switch (property.key) {
      case "cycle":
        return !cycleViewDisabled;
      case "modules":
        return !moduleViewDisabled;
      default:
        return shouldRenderDisplayProperty({ workspaceSlug: workspaceSlug?.toString(), projectId, key: property.key });
    }
  });

  return (
    <>
      <FilterHeader
        title="Display Properties"
        isPreviewEnabled={previewEnabled}
        handleIsPreviewEnabled={() => setPreviewEnabled(!previewEnabled)}
      />
      {previewEnabled && (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {filteredDisplayProperties.map((displayProperty) => (
            <>
              <button
                key={displayProperty.key}
                type="button"
                className={`rounded border px-2 py-0.5 text-xs transition-all ${
                  displayProperties?.[displayProperty.key]
                    ? "border-custom-primary-100 bg-custom-primary-100 text-white"
                    : "border-custom-border-200 hover:bg-custom-background-80"
                }`}
                onClick={() =>
                  handleUpdate({
                    [displayProperty.key]: !displayProperties?.[displayProperty.key],
                  })
                }
              >
                {displayProperty.title}
              </button>
            </>
          ))}
        </div>
      )}
    </>
  );
});
