import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import * as api from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailInboxGroup, BusinessEmailIntake } from "@/lib/business-email";
import { getChosenGrant } from "@/lib/business-grant";
import * as searchApi from "@/lib/business-search-api";
import type { BusinessSearchKind, BusinessSearchRecent, BusinessSearchResult } from "@/lib/business-search-api";
import type { ArgusLanguage } from "@/lib/language-features";
import type { BusinessApprovalAction, BusinessDossier, BusinessFactPatch } from "@/lib/business-dossier";
import { getFiscalProfile, setFiscalProfile, type FiscalProfile, type FiscalProfileInput } from "@/lib/business-dgii";
import type {
  GrantedSpace,
  BusinessAccount,
  BusinessCapturePage,
  BusinessCaptureInput,
  BusinessConsent,
  BusinessExpense,
  BusinessExpenseDetail,
  BusinessOverview,
  BusinessSpace,
  BusinessWorkspaceInfo,
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
  /** The person's acceptance of one wording of the consent screen. */
  consent: (version: string) => Promise<BusinessConsent>;
  acceptConsent: (version: string) => Promise<BusinessConsent>;
  /** Every Business the person may enter through a live grant, their own first. */
  spaces: () => Promise<GrantedSpace[]>;
  spaceDirectory?: () => Promise<api.BusinessDirectory>;
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
  setDocumentType: (id: string, version: number, documentType: "recibo" | "venta", key: string) => Promise<BusinessDossier>;
  approveDraft: (id: string, version: number, key: string, action: BusinessApprovalAction) => Promise<BusinessDossier>;
  settleRemainder: (id: string, version: number, key: string) => Promise<BusinessDossier>;
  /** The owner marks the receipt as personal or takes the mark back. */
  markPersonal: (id: string, version: number, personal: boolean, key: string) => Promise<BusinessDossier>;
  /** The accountant answers whether a personal receipt with a fiscal number goes into the 606. */
  decideFiscalInclusion: (id: string, version: number, include: boolean, key: string) => Promise<BusinessDossier>;
  receiptSource: (id: string) => Promise<Blob>;
  expenses: (from: string, to: string | null) => Promise<BusinessExpense[]>;
  expense: (id: string) => Promise<BusinessExpenseDetail>;
  search: (query: string) => Promise<BusinessSearchResult>;
  /** The next page of one list, by the cursor the last answer gave for it. */
  searchMore?: (query: string, kind: BusinessSearchKind, cursor: string) => Promise<BusinessSearchResult>;
  /** What this person searched lately; a backend without them answers 404 and the browser keeps its own. */
  searchRecents?: () => Promise<BusinessSearchRecent[]>;
  addSearchRecent?: (query: string) => Promise<void>;
  removeSearchRecent?: (id: string) => Promise<void>;
  clearSearchRecents?: () => Promise<void>;
  /** A result was opened, so it ranks first next time. Best effort. */
  recordSearchOpen?: (kind: BusinessSearchKind, id: string) => Promise<void>;
  captureNote: (input: BusinessCaptureInput, key: string) => Promise<BusinessDossier>;
  captures: (query?: string, limit?: number, view?: "inbox" | "all") => Promise<BusinessCapturePage>;
  uploadReceipt: (file: File, consentToPrepare: boolean, key: string, documentType?: "recibo" | "venta" | null, onProgress?: api.UploadProgressListener) => Promise<ReceiptSummary>;
  prepareReceipt: (id: string) => Promise<ReceiptSummary>;
  rebindReceipt: (id: string) => Promise<ReceiptDetail>;
  saveReview: (
    id: string,
    version: number,
    fields: Partial<ReceiptReviewFields>,
  ) => Promise<ReceiptDetail>;
  confirmReceipt: (id: string, version: number, key: string) => Promise<ReceiptDetail>;
  emailIntake: () => Promise<BusinessEmailIntake>;
  /** The business's name and tax id as the 606, 607 and exports print them. */
  fiscalProfile: (draftId?: string) => Promise<FiscalProfile>;
  saveFiscalProfile: (input: FiscalProfileInput, key: string) => Promise<FiscalProfile>;
  createEmailAddress: () => Promise<BusinessEmailIntake>;
  emailDeliveries: () => Promise<BusinessEmailDelivery[]>;
  emailDelivery: (id: string) => Promise<BusinessEmailDetail>;
  retryEmailDelivery: (id: string) => Promise<{ id: string }>;
  /** Inbox groups. Absent on a source that predates the call; the Bandeja then has no remitentes group. */
  emailInbox?: () => Promise<BusinessEmailInboxGroup[]>;
  setEmailSender?: typeof api.setBusinessEmailSender;
  access: () => Promise<BusinessAccess>;
  giveAccess: (email: string) => Promise<BusinessAccess>;
  resendAccessInvite: (id: string) => Promise<BusinessAccess>;
  revokeAccessGrant: (id: string) => Promise<void>;
  revokeAccessInvite: (id: string) => Promise<void>;
}>;

export const liveBusinessDataSource: BusinessDataSource = {
  mode: "live",
  ensureSpace: api.startBusinessSpace,
  consent: api.getBusinessConsent,
  acceptConsent: api.acceptBusinessConsent,
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
  setDocumentType: api.setBusinessDraftDocumentType,
  approveDraft: api.approveBusinessDraft,
  settleRemainder: api.settleBusinessRemainder,
  markPersonal: api.markBusinessPersonal,
  decideFiscalInclusion: api.decideBusinessFiscalInclusion,
  receiptSource: api.fetchBusinessReceiptSource,
  expenses: api.listBusinessExpenses,
  expense: api.getBusinessExpense,
  search: (query) => searchApi.searchBusiness(query),
  searchMore: (query, kind, cursor) => searchApi.searchBusinessMore(query, kind, cursor),
  searchRecents: searchApi.listBusinessSearchRecents,
  addSearchRecent: searchApi.addBusinessSearchRecent,
  removeSearchRecent: searchApi.removeBusinessSearchRecent,
  clearSearchRecents: searchApi.clearBusinessSearchRecents,
  recordSearchOpen: searchApi.recordBusinessSearchOpen,
  captureNote: api.captureBusinessNote,
  captures: api.listBusinessCaptures,
  uploadReceipt: api.uploadBusinessReceipt,
  prepareReceipt: api.prepareBusinessReceipt,
  rebindReceipt: api.rebindBusinessReceipt,
  saveReview: api.saveBusinessReceiptReview,
  confirmReceipt: api.confirmBusinessReceipt,
  emailIntake: api.getBusinessEmailIntake,
  fiscalProfile: getFiscalProfile,
  saveFiscalProfile: setFiscalProfile,
  createEmailAddress: api.createBusinessEmailAddress,
  emailDeliveries: api.listBusinessEmailDeliveries,
  emailDelivery: api.getBusinessEmailDelivery,
  retryEmailDelivery: api.retryBusinessEmailDelivery,
  emailInbox: api.getBusinessEmailInbox,
  setEmailSender: api.setBusinessEmailSender,
  access: api.getBusinessAccess,
  giveAccess: api.giveBusinessAccess,
  resendAccessInvite: api.resendBusinessAccessInvite,
  revokeAccessGrant: api.revokeBusinessAccessGrant,
  revokeAccessInvite: api.revokeBusinessAccessInvite,
  spaces: api.getBusinessSpaces,
  spaceDirectory: api.getBusinessDirectory,
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
  let generation = browserAuthGeneration();
  const ready = () => {
    const grant = getChosenGrant();
    const currentGeneration = browserAuthGeneration();
    if (generation !== currentGeneration) {
      started = null;
      generation = currentGeneration;
    }
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
      const requestGeneration = browserAuthGeneration();
      await ready();
      requireBrowserAuthGeneration(requestGeneration);
      return call(...args);
    };
  return {
    mode: source.mode,
    ensureSpace: ready,
    consent: source.consent,
    acceptConsent: source.acceptConsent,
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
    setDocumentType: source.setDocumentType,
    approveDraft: source.approveDraft,
    settleRemainder: source.settleRemainder,
    markPersonal: source.markPersonal,
    decideFiscalInclusion: source.decideFiscalInclusion,
    receiptSource: source.receiptSource,
    expenses: after(source.expenses),
    search: after(source.search),
    searchMore: source.searchMore ? after(source.searchMore) : undefined,
    searchRecents: source.searchRecents ? after(source.searchRecents) : undefined,
    addSearchRecent: source.addSearchRecent ? after(source.addSearchRecent) : undefined,
    removeSearchRecent: source.removeSearchRecent ? after(source.removeSearchRecent) : undefined,
    clearSearchRecents: source.clearSearchRecents ? after(source.clearSearchRecents) : undefined,
    recordSearchOpen: source.recordSearchOpen ? after(source.recordSearchOpen) : undefined,
    captureNote: source.captureNote,
    captures: source.captures,
    uploadReceipt: after(source.uploadReceipt),
    prepareReceipt: source.prepareReceipt,
    rebindReceipt: source.rebindReceipt,
    saveReview: source.saveReview,
    confirmReceipt: source.confirmReceipt,
    emailIntake: after(source.emailIntake),
    fiscalProfile: after(source.fiscalProfile),
    saveFiscalProfile: source.saveFiscalProfile,
    createEmailAddress: after(source.createEmailAddress),
    emailDeliveries: after(source.emailDeliveries),
    emailDelivery: source.emailDelivery,
    retryEmailDelivery: source.retryEmailDelivery,
    emailInbox: source.emailInbox ? after(source.emailInbox) : undefined,
    setEmailSender: source.setEmailSender ? after(source.setEmailSender) : undefined,
    access: after(source.access),
    giveAccess: after(source.giveAccess),
    resendAccessInvite: after(source.resendAccessInvite),
    revokeAccessGrant: source.revokeAccessGrant,
    revokeAccessInvite: source.revokeAccessInvite,
    spaces: after(source.spaces),
    spaceDirectory: source.spaceDirectory,
    markAccessSeen: source.markAccessSeen,
  };
}

/** The type most of the Business's accounts have, so a new one starts there; none on a tie. */
export function preferredAccountType(accounts: readonly BusinessAccount[]): api.ExpenseAccountType | null {
  const counts = new Map<api.ExpenseAccountType, number>();
  for (const { type } of accounts) {
    const known = api.EXPENSE_ACCOUNT_TYPES.find((item) => item === type);
    if (known) counts.set(known, (counts.get(known) ?? 0) + 1);
  }
  const ranked = [...counts].sort((a, b) => b[1] - a[1]);
  return ranked.length > 0 && ranked[0][1] !== ranked[1]?.[1] ? ranked[0][0] : null;
}
