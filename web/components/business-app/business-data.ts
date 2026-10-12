import * as api from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailIntake } from "@/lib/business-email";
import type { ArgusLanguage } from "@/lib/language-features";
import type { BusinessDossier, BusinessFactPatch } from "@/lib/business-dossier";
import type {
  BusinessAccount,
  BusinessCapture,
  BusinessCaptureInput,
  BusinessExpense,
  BusinessOverview,
  BusinessSearchResult,
  BusinessSpace,
  BusinessUpdate,
  BusinessWorkspaceInfo,
  ExpenseInput,
  ReceiptDetail,
  ReceiptReviewFields,
  ReceiptSummary,
} from "@/lib/business-api";

/**
 * Everything the Business screens read or write. The live source is the API;
 * the fixture source exists only for the local design preview and says so.
 */
export type BusinessDataSource = Readonly<{
  mode: "live" | "fixture";
  ensureSpace: (language: ArgusLanguage) => Promise<BusinessSpace>;
  workspace: () => Promise<BusinessWorkspaceInfo>;
  overview: (from: string, to: string) => Promise<BusinessOverview>;
  receipts: (view: "inbox" | "all") => Promise<ReceiptSummary[]>;
  receipt: (id: string) => Promise<ReceiptDetail>;
  dossier: (id: string) => Promise<BusinessDossier>;
  reviewDraft: (id: string, version: number, facts: BusinessFactPatch, key: string) => Promise<BusinessDossier>;
  approveDraft: (id: string, version: number, key: string) => Promise<BusinessDossier>;
  receiptSource: (id: string) => Promise<Blob>;
  updates: () => Promise<BusinessUpdate[]>;
  expenses: (from: string, to: string) => Promise<BusinessExpense[]>;
  search: (query: string) => Promise<BusinessSearchResult>;
  captureNote: (input: BusinessCaptureInput, key: string) => Promise<BusinessDossier>;
  captures: (query?: string, limit?: number) => Promise<BusinessCapture[]>;
  uploadReceipt: (file: File, consentToPrepare: boolean, key: string) => Promise<ReceiptSummary>;
  prepareReceipt: (id: string) => Promise<ReceiptSummary>;
  saveReview: (
    id: string,
    version: number,
    fields: Partial<ReceiptReviewFields>,
  ) => Promise<ReceiptDetail>;
  confirmReceipt: (id: string, version: number, key: string) => Promise<ReceiptDetail>;
  recordExpense: (input: ExpenseInput, key: string) => Promise<BusinessExpense>;
  createAccount: (
    input: { nickname: string; type: string; currency: string },
    key: string,
  ) => Promise<BusinessAccount>;
  emailIntake: () => Promise<BusinessEmailIntake>;
  createEmailAddress: () => Promise<BusinessEmailIntake>;
  emailDeliveries: () => Promise<BusinessEmailDelivery[]>;
  emailDelivery: (id: string) => Promise<BusinessEmailDetail>;
  retryEmailDelivery: (id: string) => Promise<{ id: string }>;
}>;

export const liveBusinessDataSource: BusinessDataSource = {
  mode: "live",
  ensureSpace: api.startBusinessSpace,
  workspace: api.getBusinessWorkspace,
  overview: api.getBusinessOverview,
  receipts: api.listBusinessReceipts,
  receipt: api.getBusinessReceipt,
  dossier: api.getBusinessDossier,
  reviewDraft: api.reviewBusinessDraft,
  approveDraft: api.approveBusinessDraft,
  receiptSource: api.fetchBusinessReceiptSource,
  updates: api.listBusinessUpdates,
  expenses: api.listBusinessExpenses,
  search: (query) => api.searchBusiness(query),
  captureNote: api.captureBusinessNote,
  captures: api.listBusinessCaptures,
  uploadReceipt: api.uploadBusinessReceipt,
  prepareReceipt: api.prepareBusinessReceipt,
  saveReview: api.saveBusinessReceiptReview,
  confirmReceipt: api.confirmBusinessReceipt,
  recordExpense: api.recordBusinessExpense,
  createAccount: api.createBusinessAccount,
  emailIntake: api.getBusinessEmailIntake,
  createEmailAddress: api.createBusinessEmailAddress,
  emailDeliveries: api.listBusinessEmailDeliveries,
  emailDelivery: api.getBusinessEmailDelivery,
  retryEmailDelivery: api.retryBusinessEmailDelivery,
};

export function withBusinessSpace(
  source: BusinessDataSource,
  language: () => ArgusLanguage,
): BusinessDataSource {
  let started: Promise<BusinessSpace> | null = null;
  const ready = () => {
    started ??= source.ensureSpace(language()).catch((error: unknown) => {
      started = null;
      throw error;
    });
    return started;
  };
  const after =
    <A extends unknown[], R>(call: (...args: A) => Promise<R>) =>
    async (...args: A): Promise<R> => {
      await ready();
      return call(...args);
    };
  return {
    mode: source.mode,
    ensureSpace: ready,
    workspace: after(source.workspace),
    overview: after(source.overview),
    receipts: after(source.receipts),
    receipt: source.receipt,
    dossier: source.dossier,
    reviewDraft: source.reviewDraft,
    approveDraft: source.approveDraft,
    receiptSource: source.receiptSource,
    updates: after(source.updates),
    expenses: after(source.expenses),
    search: after(source.search),
    captureNote: source.captureNote,
    captures: source.captures,
    uploadReceipt: after(source.uploadReceipt),
    prepareReceipt: source.prepareReceipt,
    saveReview: source.saveReview,
    confirmReceipt: source.confirmReceipt,
    recordExpense: after(source.recordExpense),
    createAccount: after(source.createAccount),
    emailIntake: after(source.emailIntake),
    createEmailAddress: after(source.createEmailAddress),
    emailDeliveries: after(source.emailDeliveries),
    emailDelivery: source.emailDelivery,
    retryEmailDelivery: source.retryEmailDelivery,
  };
}
