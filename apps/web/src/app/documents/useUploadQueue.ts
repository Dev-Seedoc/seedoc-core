import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useCreateDocument } from "@/lib/api/hooks/documents";
import { queryKeys } from "@/lib/api/queryKeys";
import type { AccessLevel, DocType, DocumentRead } from "@/lib/api/types";

import { getUploadErrorMessage, usePdfUpload } from "./usePdfUpload";

// Uploads run side by side up to this many: quicker than one by one, without flooding the browser or the store.
const PARALLEL_UPLOADS = 3;

// One file on its way (API.md §3.3): hash → create_upload → PUT → create_document.
export type UploadPhase =
  | { name: "waiting" }
  | { name: "hashing" }
  | { name: "uploading"; progress: number }
  | { name: "creating" }
  | { name: "done"; document: DocumentRead }
  | { name: "failed"; message: string };

export interface UploadJob {
  key: string;
  file: File;
  title: string;
  phase: UploadPhase;
}

// What every new document of this upload gets.
export interface UploadValues {
  folderId: string;
  docType: DocType;
  language: string;
  accessLevel: AccessLevel;
}

const BUSY_PHASES = new Set<UploadPhase["name"]>(["waiting", "hashing", "uploading", "creating"]);

export function isUploadBusy(job: UploadJob): boolean {
  return BUSY_PHASES.has(job.phase.name);
}

export function useUploadQueue(tenantId: string) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const uploadPdf = usePdfUpload(tenantId);
  const createDocument = useCreateDocument(tenantId);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  // The values of the last start, so "Erneut versuchen" uploads failed files the same way.
  const valuesRef = useRef<UploadValues | null>(null);

  function setPhase(key: string, phase: UploadPhase) {
    setJobs((current) => current.map((job) => (job.key === key ? { ...job, phase } : job)));
  }

  // Returns how the file ended: "done" or "failed".
  async function runJob(job: UploadJob, values: UploadValues): Promise<UploadPhase> {
    try {
      const uploadId = await uploadPdf(job.file, (step) => {
        setPhase(job.key, step);
      });
      setPhase(job.key, { name: "creating" });
      const document = await createDocument.mutateAsync({
        upload_id: uploadId,
        folder_id: values.folderId,
        title: job.title.trim(),
        doc_type: values.docType,
        language: values.language,
        access_level: values.accessLevel,
      });
      const done = { name: "done", document } as const;
      setPhase(job.key, done);
      return done;
    } catch (error) {
      const failed = { name: "failed", message: getUploadErrorMessage(error, t) } as const;
      setPhase(job.key, failed);
      return failed;
    }
  }

  // Runs `toRun` with at most PARALLEL_UPLOADS at a time, then reloads every document list once.
  async function run(toRun: UploadJob[], values: UploadValues): Promise<UploadPhase[]> {
    const queue = [...toRun];
    const outcomes: UploadPhase[] = [];
    const worker = async () => {
      for (let job = queue.shift(); job; job = queue.shift()) {
        outcomes.push(await runJob(job, values));
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALLEL_UPLOADS, queue.length) }, worker));
    await queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allDocuments(tenantId) });
    return outcomes;
  }

  async function start(files: Omit<UploadJob, "phase">[], values: UploadValues): Promise<UploadPhase[]> {
    valuesRef.current = values;
    const newJobs = files.map((file) => ({ ...file, phase: { name: "waiting" } as const }));
    setJobs(newJobs);
    return run(newJobs, values);
  }

  // Runs every failed file again from the start (a new upload: the old upload URL may have expired).
  async function retryFailed(): Promise<UploadPhase[]> {
    const values = valuesRef.current;
    const failed = jobs.filter((job) => job.phase.name === "failed");
    if (!values || failed.length === 0) {
      return [];
    }
    setJobs((current) =>
      current.map((job) => (job.phase.name === "failed" ? { ...job, phase: { name: "waiting" } } : job)),
    );
    return run(failed, values);
  }

  return { jobs, isBusy: jobs.some(isUploadBusy), start, retryFailed };
}
