import React, { useState, useEffect } from "react";
import { Pencil } from "lucide-react";
import axios from "axios";
import { Input } from "@plane/ui";

export type CustomProperty = {
  key: string;
  value: string;
  issue_type_custom_property: string;
  is_required: boolean;
  name: string;
  id: string;
  data_type: string;
  is_active: boolean;
};

type IssueTypeCustomProperty = {
  id: string;
  name: string;
  data_type: string;
  is_required: boolean;
  is_active: boolean;
  value: any;
};

type CustomPropertiesProps = {
  customProperties?: CustomProperty[];
  issue_type_id: string;
  workspaceSlug: string;
  updateCustomProperties: (updatedProperties: CustomProperty[]) => void;
  layout?: "quarter" | "two-fifths";
  issueData?: {
    reference_number?: string;
  };
};

export const CustomProperties: React.FC<CustomPropertiesProps> = ({
  customProperties,
  issue_type_id,
  workspaceSlug,
  updateCustomProperties,
  layout = "quarter",
  issueData,
}) => {
  const [issueTypeCustomProperties, setissueTypeCustomProperties] = useState<IssueTypeCustomProperty[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingPropertyKey, setEditingPropertyKey] = useState<string | null>(null);
  const [localCustomProperties, setLocalCustomProperties] = useState<CustomProperty[]>([]);
  const [dropdownOptions, setDropdownOptions] = useState<Record<string, { value: string; label: string }[]>>({});
  const [loadingDropdowns, setLoadingDropdowns] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const getIssueTypeCustomProperties = async () => {
      try {
        const response = await axios.get(
          `/api/workspaces/${workspaceSlug}/issue-type/${issue_type_id}/custom-properties/`,
        );
        setissueTypeCustomProperties(response.data);
        setError(null);
      } catch (error) {
        setError("Failed to load custom properties.");
      }
    };

    if (!issue_type_id) {
      setError("Invalid Issue Type");
      return;
    }

    getIssueTypeCustomProperties();
  }, [workspaceSlug, issue_type_id]);

  useEffect(() => {
    if (customProperties) {
      setLocalCustomProperties(customProperties);
    }
  }, [customProperties]);

  // Fetch dropdown options for dropdown type custom properties
  useEffect(() => {
    const fetchDropdownOptions = async () => {
      if (!issueTypeCustomProperties || issueTypeCustomProperties.length === 0) {
        return;
      }

      const dropdownProperties = issueTypeCustomProperties.filter(
        (prop) => prop.data_type === "dropdown"
      );

      for (const prop of dropdownProperties) {
        try {
          // Parse dropdown configuration from value field
          const dropdownConfig = prop.value;
          if (!dropdownConfig || typeof dropdownConfig !== "object") {
            continue;
          }

          const identifier = dropdownConfig.dropdown_source_field;
          if (!identifier) {
            continue;
          }

          // Set loading state
          setLoadingDropdowns((prev) => ({ ...prev, [prop.id]: true }));

          // Build query parameters
          const params = new URLSearchParams({
            issue_type_id: issue_type_id,
            issue_type_custom_property_id: prop.id,
            custom_property_id: prop.id,
          });

          // Add reference_number for system type dropdowns
          if (
            dropdownConfig.dropdown_source_type === "system" &&
            issueData?.reference_number
          ) {
            params.append("reference_number", issueData.reference_number);
          }

          // Fetch dropdown options
          const response = await axios.get(
            `/api/workspaces/${workspaceSlug}/issue/dropdown-options/${identifier}/?${params.toString()}`
          );

          // Update dropdown options state
          if (response.data && Array.isArray(response.data.options)) {
            setDropdownOptions((prev) => ({
              ...prev,
              [prop.id]: response.data.options,
            }));
          }
        } catch (error) {
          console.error(`Failed to fetch dropdown options for ${prop.name}:`, error);
          // On error, set empty options (will fall back to text input)
          setDropdownOptions((prev) => ({ ...prev, [prop.id]: [] }));
        } finally {
          // Clear loading state
          setLoadingDropdowns((prev) => ({ ...prev, [prop.id]: false }));
        }
      }
    };

    fetchDropdownOptions();
  }, [issueTypeCustomProperties, workspaceSlug, issue_type_id, issueData?.reference_number]);

  const mergedCustomProperties = issueTypeCustomProperties
    .filter((customProp) => customProp.is_active)
    .map((customProp) => {
      const customProperty = localCustomProperties?.find((prop) => prop.key === customProp.name);

      return {
        key: customProp.name,
        value: customProperty ? customProperty.value : "",
        issue_type_custom_property: customProp.id,
        is_required: customProp.is_required,
        id: customProperty ? customProperty.id : "",
        name: customProp.name,
        data_type: customProp.data_type,
        is_active: customProp.is_active,
      };
    });

  if (error) {
    return <div className="text-red-500 text-sm mt-1">{error}</div>;
  }

  if (!Array.isArray(mergedCustomProperties) || mergedCustomProperties.length === 0) {
    return null;
  }

  const handlePropertyUpdate = async (updatedProperty: CustomProperty) => {
    try {
      setLocalCustomProperties(prev => {
        const updatedProperties = [...(prev || [])];
        const existingIndex = updatedProperties.findIndex(p => p.key === updatedProperty.key);
        
        if (existingIndex >= 0) {
          updatedProperties[existingIndex] = {...updatedProperties[existingIndex], ...updatedProperty};
        } else {
          updatedProperties.push(updatedProperty);
        }
        
        return updatedProperties;
      });
      
      await updateCustomProperties([updatedProperty]);
    } catch (error) {
      console.error("Failed to update custom property:", error);
    }
  };

  const EditableProperty: React.FC<{ property: CustomProperty }> = React.memo(({ property }) => {
    const [value, setValue] = useState(property.value);
    const [localError, setLocalError] = useState<string | null>(null);

    const handleBlur = async () => {
      if (property.is_required && value.trim() === "") {
        setLocalError("This field is required and cannot be left empty or consist of spaces.");
        setValue(property.value);
        return;
      }

      if (value !== property.value) {
        try {
          const updatedProperty = { ...property, value };
          await handlePropertyUpdate(updatedProperty);
          setLocalError(null);
        } catch (error) {
          setLocalError("Failed to update custom property.");
        }
      }

      setEditingPropertyKey(null);
      setLocalError(null);
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setValue(e.target.value);
      setLocalError(null);
    };

    const inputComponents: Record<string, React.JSX.Element> = {
      date: (
        <Input
          type="date"
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          autoFocus
          placeholder={`Add ${property.key}`}
          className="text-sm w-full border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-custom-primary-100"
        />
      ),
      boolean: (
        <select
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          autoFocus
          className="text-sm w-full border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-custom-primary-100"
        >
          <option value="">Select {property.key}</option>
          <option value="true">True</option>
          <option value="false">False</option>
        </select>
      ),
      number: (
        <Input
          type="number"
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          autoFocus
          placeholder={`Add ${property.key}`}
          className="text-sm w-full border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-custom-primary-100"
        />
      ),
      text: (
        <Input
          type="text"
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          autoFocus
          placeholder={`Add ${property.key}`}
          className="text-sm w-full border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-custom-primary-100"
        />
      ),
      dropdown: (() => {
        const isLoading = loadingDropdowns[property.issue_type_custom_property];
        const options = dropdownOptions[property.issue_type_custom_property] || [];
        
        // Show loading state
        if (isLoading) {
          return (
            <select
              disabled
              className="text-sm w-full border rounded px-2 py-1 bg-custom-background-80 cursor-not-allowed"
            >
              <option>Loading options...</option>
            </select>
          );
        }
        
        // Show dropdown if options are available
        if (options.length > 0) {
          return (
            <select
              value={value}
              onChange={handleChange}
              onBlur={handleBlur}
              autoFocus
              className="text-sm w-full border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-custom-primary-100"
            >
              <option value="">Select {property.key}</option>
              {options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          );
        }
        
        // Fallback to text input if no options available
        return (
          <Input
            type="text"
            value={value}
            onChange={handleChange}
            onBlur={handleBlur}
            autoFocus
            placeholder={`Add ${property.key}`}
            className="text-sm w-full border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-custom-primary-100"
          />
        );
      })(),
    };
    
    return (
      <div>
        {inputComponents[property?.data_type as keyof typeof inputComponents] || inputComponents.text}
        {localError && (
          <div className="text-red-500 text-sm mt-1">{localError}</div>
        )}
      </div>
    );
  });

  const labelWidth = layout === "two-fifths" ? "w-2/5" : "w-1/4";
  const valueWidth = layout === "two-fifths" ? "w-3/5" : "w-3/4";

  return (
    <div className="w-full">
      <hr className="flex-shrink-0 border-custom-sidebar-border-300 h-[0.5px] w-full mx-auto my-1" />

      <div className="space-y-2">
        {mergedCustomProperties.map((element) => (
          <div key={element.key} className="flex w-full items-center gap-3 min-h-8">
            <div className={`flex items-center gap-1 ${labelWidth} flex-shrink-0 text-sm text-custom-text-300 truncate`}>
              <span>
                {element.key}
                {element.is_required && <span className="text-red-500 ml-1">*</span>}
              </span>
            </div>
            <div className={`${valueWidth} flex-grow group text-sm`}>
              {editingPropertyKey === element.key ? (
                <EditableProperty property={element} />
              ) : (
                <button
                  type="button"
                  className="group flex items-center justify-between gap-2 px-2 py-0.5 rounded outline-none w-full hover:bg-custom-background-80"
                  onClick={() => setEditingPropertyKey(element.key)}
                >
                  {element.value ? (
                    <span className="text-sm text-custom-text-500 whitespace-nowrap overflow-hidden text-ellipsis" title={element.value}>
                      {element.value}
                    </span>
                  ) : (
                    <span className="text-sm text-custom-text-400">Add {element.key}</span>
                  )}
                  <span className="p-1 flex-shrink-0 opacity-0 group-hover:opacity-100 text-custom-text-400">
                    <Pencil className="h-2.5 w-2.5 flex-shrink-0" />
                  </span>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};