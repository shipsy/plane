"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Dialog, Transition } from "@headlessui/react";
import useSWR from "swr";
// types
import { IExportData, IExportServiceResponse } from "@plane/types";
// ui
import { Button, Loader } from "@plane/ui";
// components
import { SingleExport } from "./single-export";
// services
import { ProjectExportService } from "@/services/project";

type Props = {
  isOpen: boolean;
  handleClose: () => void;
};

const projectExportService = new ProjectExportService();
const PER_PAGE = 10;

export const ExportHistory: React.FC<Props> = ({ isOpen, handleClose }) => {
  const { workspaceSlug } = useParams();
  const [cursor, setCursor] = useState<string>(`${PER_PAGE}:0:0`);

  const swrKey = workspaceSlug && isOpen ? `EXPORT_HISTORY_${workspaceSlug}_${cursor}` : null;

  const { data, isValidating, mutate } = useSWR<IExportServiceResponse>(
    swrKey,
    () => projectExportService.getExportsServicesList(workspaceSlug as string, cursor, PER_PAGE)
  );

  const results: IExportData[] = data?.results ?? [];
  const hasProcessing = useMemo(
    () => results.some((r) => r.status === "queued" || r.status === "processing"),
    [results]
  );

  // Poll every 3s while anything is processing
  useEffect(() => {
    if (!isOpen || !hasProcessing) return;
    const id = setInterval(() => {
      mutate();
    }, 3000);
    return () => clearInterval(id);
  }, [isOpen, hasProcessing, mutate]);

  return (
    <Transition.Root show={isOpen} as={React.Fragment}>
      <Dialog as="div" className="relative z-20" onClose={handleClose}>
        <Transition.Child
          as={React.Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-custom-backdrop transition-opacity" />
        </Transition.Child>

        <div className="fixed inset-0 z-20 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
            <Transition.Child
              as={React.Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="relative transform rounded-lg bg-custom-background-100 text-left shadow-custom-shadow-md transition-all sm:my-8 sm:w-full sm:max-w-2xl">
                <div className="flex items-center justify-between border-b border-custom-border-200 px-6 py-4">
                  <h3 className="text-lg font-medium">Export history</h3>
                  <Button variant="neutral-primary" size="sm" onClick={handleClose}>
                    Close
                  </Button>
                </div>
                <div className="max-h-[70vh] overflow-y-auto divide-y divide-custom-border-200">
                  {!data ? (
                    <div className="p-4">
                      <Loader className="space-y-2">
                        <Loader.Item height="40px" />
                        <Loader.Item height="40px" />
                        <Loader.Item height="40px" />
                      </Loader>
                    </div>
                  ) : results.length === 0 ? (
                    <div className="px-6 py-10 text-center text-sm text-custom-text-200">
                      No exports yet. Trigger one from the Download menu.
                    </div>
                  ) : (
                    results.map((service) => (
                      <SingleExport key={service.id} service={service} refreshing={isValidating} />
                    ))
                  )}
                </div>
                {data && (data.prev_page_results || data.next_page_results) && (
                  <div className="flex items-center justify-between border-t border-custom-border-200 px-6 py-3">
                    <Button
                      variant="neutral-primary"
                      size="sm"
                      disabled={!data.prev_page_results}
                      onClick={() => setCursor(data.prev_cursor)}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="neutral-primary"
                      size="sm"
                      disabled={!data.next_page_results}
                      onClick={() => setCursor(data.next_cursor)}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};
