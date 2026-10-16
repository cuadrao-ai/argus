import * as api from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailIntake } from "@/lib/business-email";
import { getChosenGrant } from "@/lib/business-grant";
import type { ArgusLanguage } from "@/lib/language-features";
import type { BusinessDossier, BusinessFactPatch } from "@/lib/business-dossier";
import type {
  GrantedSpace,
  BusinessAccount,
  BusinessCapture,
  BusinessCaptureInput,
  BusinessExpense,
  BusinessExpenseDetail,
  BusinessOverview,
  BusinessSearchResult,
  BusinessSpace,
  BusinessUpdate,
  BusinessWorkspaceInfo,
  ExpenseInput,
  NewBusinessAccount,
  ReceiptDetail,
  ReceiptReviewFields,
  ReceiptSummary,
  BusinessAccess,
} from "@/lib/business-api";

/**
 * Everything the Business screens read or write. The live source is the API;
 * the fixture source exists only for the local design preview and says so.
 */
export type BusinessDataSource = Readonly<{
  mode: "live" | "fixture";
  ensureSpace: (language: ArgusLanguage) => Promise<BusinessSpace>;
  /** Every Business the person may enter through a live grant, their own first. */
  spaces: () => Promise<GrantedSpace[]>;
  /** The person dismissed the one-time access line for one of their grants. */
  markAccessSeen: (grantId: string) => Promise<void>;
  workspace: () => Promise<BusinessWorkspaceInfo>;
  receiptActivity?: typeof api.getReceiptActivity;
  receiptPage?: typeof api.getBusinessReceiptPage;
  receiptReading?: typeof api.getReceiptReading;
  setReceiptReading?: typeof api.setReceiptReading;
  markReceiptRead?: typeof api.markReceiptRead;
  overview: (from: string, to: string | null) => Promise<BusinessOverview>;
  receipts: (view: "inbox" | "all") => Promise<ReceiptSummary[]>;
  receipt: (id: string, signal?: AbortSignal) => Promise<ReceiptDetail>;
  dossier: (id: string) => Promise<BusinessDossier>;
  reviewDraft: (id: string, version: number, facts: BusinessFactPatch, key: string) => Promise<BusinessDossier>;
  approveDraft: (id: string, version: number, key: string) => Promise<BusinessDossier>;
  settleRemainder: (id: string, version: number, key: string) => Promise<BusinessDossier>;
  /** The owner marks the receipt as personal or takes the mark back. */
  markPersonal: (id: string, version: number, personal: boolean, key: string) => Promise<BusinessDossier>;
  /** The accountant answers whether a personal receipt with a fiscal number goes into the 606. */
  decideFiscalInclusion: (id: string, version: number, include: boolean, key: string) => Promise<BusinessDossier>;
  receiptSource: (id: string) => Promise<Blob>;
  updates: () => Promise<BusinessUpdate[]>;
  expenses: (from: string, to: string | null) => Promise<BusinessExpense[]>;
  expense: (id: string) => Promise<BusinessExpenseDetail>;
  search: (query: string) => Promise<BusinessSearchResult>;
  captureNote: (input: BusinessCaptureInput, key: string) => Promise<BusinessDossier>;
  captures: (query?: string, limit?: number, view?: "inbox" | "all") => Promise<BusinessCapture[]>;
  uploadReceipt: (file: File, consentToPrepare: boolean, key: string) => Promise<ReceiptSummary>;
  prepareReceipt: (id: string) => Promise<ReceiptSummary>;
  rebindReceipt: (id: string) => Promise<ReceiptDetail>;
  saveReview: (
    id: string,
    version: number,
    fields: Partial<ReceiptReviewFields>,
  ) => Promise<ReceiptDetail>;
  confirmReceipt: (id: string, version: number, key: string) => Promise<ReceiptDetail>;
  recordExpense: (input: ExpenseInput, key: string) => Promise<BusinessExpense>;
  createAccount: (input: NewBusinessAccount, key: string) => Promise<BusinessAccount>;
  emailIntake: () => Promise<BusinessEmailIntake>;
  createEmailAddress: () => Promise<BusinessEmailIntake>;
  emailDeliveries: () => Promise<BusinessEmailDelivery[]>;
  emailDelivery: (id: string) => Promise<BusinessEmailDetail>;
  retryEmailDelivery: (id: string) => Promise<{ id: string }>;
  access: () => Promise<BusinessAccess>;
  giveAccess: (email: string) => Promise<BusinessAccess>;
  revokeAccessGrant: (id: string) => Promise<void>;
  revokeAccessInvite: (id: string) => Promise<void>;
}>;

export const liveBusinessDataSource: BusinessDataSource = {
  mode: "live",
  ensureSpace: api.startBusinessSpace,
  workspace: api.getBusinessWorkspace,
  receiptActivity: api.getReceiptActivity,
  receiptPage: api.getBusinessReceiptPage,
  receiptReading: api.getReceiptReading,
  setReceiptReading: api.setReceiptReading,
  markReceiptRead: api.markReceiptRead,
  overview: api.getBusinessOverview,
  receipts: api.listBusinessReceipts,
  receipt: api.getBusinessReceipt,
  dossier: api.getBusinessDossier,
  reviewDraft: api.reviewBusinessDraft,
  approveDraft: api.approveBusinessDraft,
  settleRemainder: api.settleBusinessRemainder,
  markPersonal: api.markBusinessPersonal,
  decideFiscalInclusion: api.decideBusinessFiscalInclusion,
  receiptSource: api.fetchBusinessReceiptSource,
  updates: api.listBusinessUpdates,
  expenses: api.listBusinessExpenses,
  expense: api.getBusinessExpense,
  search: (query) => api.searchBusiness(query),
  captureNote: api.captureBusinessNote,
  captures: api.listBusinessCaptures,
  uploadReceipt: api.uploadBusinessReceipt,
  prepareReceipt: api.prepareBusinessReceipt,
  rebindReceipt: api.rebindBusinessReceipt,
  saveReview: api.saveBusinessReceiptReview,
  confirmReceipt: api.confirmBusinessReceipt,
  recordExpense: api.recordBusinessExpense,
  createAccount: api.createBusinessAccount,
  emailIntake: api.getBusinessEmailIntake,
  createEmailAddress: api.createBusinessEmailAddress,
  emailDeliveries: api.listBusinessEmailDeliveries,
  emailDelivery: api.getBusinessEmailDelivery,
  retryEmailDelivery: api.retryBusinessEmailDelivery,
  access: api.getBusinessAccess,
  giveAccess: api.giveBusinessAccess,
  revokeAccessGrant: api.revokeBusinessAccessGrant,
  revokeAccessInvite: api.revokeBusinessAccessInvite,
  spaces: api.getBusinessSpaces,
  markAccessSeen: api.markBusinessAccessSeen,
};

export function withBusinessSpace(
  source: BusinessDataSource,
  language: () => ArgusLanguage,
): BusinessDataSource {
  // One bootstrap per Business the person works in: the own space is started
  // once; a client's Business exists already and is never started by its
  // accountant, so under a chosen grant the calls go straight through.
  let started: Promise<BusinessSpace> | null = null;
  let startedFor: string | null = null;
  const ready = () => {
    const grant = getChosenGrant();
    if (grant) return Promise.resolve({ id: "", name: "" } as BusinessSpace);
    if (startedFor !== grant) {
      started = null;
      startedFor = grant;
    }
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
    receiptActivity: source.receiptActivity ? after(source.receiptActivity) : undefined,
    receiptPage: source.receiptPage ? after(source.receiptPage) : undefined,
    receiptReading: source.receiptReading ? after(source.receiptReading) : undefined,
    setReceiptReading: source.setReceiptReading,
    markReceiptRead: source.markReceiptRead,
    overview: after(source.overview),
    receipts: after(source.receipts),
    receipt: source.receipt,
    expense: source.expense,
    dossier: source.dossier,
    reviewDraft: source.reviewDraft,
    approveDraft: source.approveDraft,
    settleRemainder: source.settleRemainder,
    markPersonal: source.markPersonal,
    decideFiscalInclusion: source.decideFiscalInclusion,
    receiptSource: source.receiptSource,
    updates: after(source.updates),
    expenses: after(source.expenses),
    search: after(source.search),
    captureNote: source.captureNote,
    captures: source.captures,
    uploadReceipt: after(source.uploadReceipt),
    prepareReceipt: source.prepareReceipt,
    rebindReceipt: source.rebindReceipt,
    saveReview: source.saveReview,
    confirmReceipt: source.confirmReceipt,
    recordExpense: after(source.recordExpense),
    createAccount: after(source.createAccount),
    emailIntake: after(source.emailIntake),
    createEmailAddress: after(source.createEmailAddress),
    emailDeliveries: after(source.emailDeliveries),
    emailDelivery: source.emailDelivery,
    retryEmailDelivery: source.retryEmailDelivery,
    access: after(source.access),
    giveAccess: after(source.giveAccess),
    revokeAccessGrant: source.revokeAccessGrant,
    revokeAccessInvite: source.revokeAccessInvite,
    spaces: after(source.spaces),
    markAccessSeen: source.markAccessSeen,
  };
}
