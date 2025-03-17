import React, { useState } from "react";

export type CustomProperty = {
  key: string;
  value: string;
  issue_type_custom_property: string;
};

type CustomPropertiesProps = {
  customProperties?: CustomProperty[];
  // A function from the parent that calls issueOperations.update
  updateCustomProperties: (updatedProperties: CustomProperty[]) => void;
};

export const CustomProperties: React.FC<CustomPropertiesProps> = ({ customProperties, updateCustomProperties }) => {
  if (!Array.isArray(customProperties) || customProperties.length === 0) {
    return null; 
  }

  // Inline editable component for each property
  const EditableProperty: React.FC<{ property: CustomProperty }> = ({ property }) => {
    const [value, setValue] = useState(property.value);

    const handleBlur = () => {
      // Only update if the value has actually changed
      if (value !== property.value) {
        // Build an updated properties array
        const updated = customProperties.map((prop) =>
          prop.key === property.key ? { ...prop, value } : prop
        );
        updateCustomProperties(updated);
      }
    };

    return (
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        className="text-sm border rounded px-1 py-0.5"
      />
    );
  };

  return (
    <div className="w-full">
      <hr className="border-custom-sidebar-border-300 h-[0.5px] w-full mx-auto my-1" />
      {customProperties.map((element) => (
        <div key={element.key} className="flex min-h-8 gap-2 items-center">
          <div className="w-2/5 text-sm text-custom-text-300">{element.key}</div>
          <div className="w-3/5 ml-5">
            <EditableProperty property={element} />
          </div>
        </div>
      ))}
    </div>
  );
};
