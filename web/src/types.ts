// Типы повторяют DTO API кампаний (task.md §2–3) и ответ агента.

export type State =
  | "DRAFT" | "ON_MODERATION" | "NEEDS_WORK" | "APPROVED"
  | "ACTIVE" | "ACTIVE_EDITING" | "STOPPED" | "ARCHIVED";

export type Role = "campaignManager" | "campaignModerator";

export interface Link { iOS?: string; android?: string; web?: string }
export interface TextStyle { fontSize?: number; fontWeight?: string; textColor?: string }

export interface BannerContent {
  title?: string;
  text?: string;
  titleStyle?: TextStyle;
  textStyle?: TextStyle;
  background?: { color?: string };
  image?: { url?: string };
  buttonName?: string;
  actionType: string;
  link?: Link;
  voiceOver?: string;
}

export interface PromoComponent {
  role: "text" | "image" | "button";
  format?: "none" | "html";
  text?: string;
  textStyle?: TextStyle;
  url?: string;
  aspectRatio?: number;
  actionType?: string;
  link?: Link;
  style?: { backgroundColor?: string };
}

export interface PromoContent {
  role: "promo";
  component: {
    role: "linearContainer";
    axis: "v";
    aligns?: string;
    style?: { backgroundColor?: string };
    components: PromoComponent[];
  };
}

export interface Banner { id: number; campaignId: number; name: string; bannerTypeId: number; content: BannerContent }
export interface Content { id: number; campaignId: number; name: string; contentType: "PROMO"; content: PromoContent }
export interface Creative { id: number; campaignId: number; name: string; bannerId: number; contentId?: number; channelCode: string }

export interface Campaign {
  id: number;
  name: string;
  marketingName?: string;
  startDate: string;
  startTime: string;
  endDate?: string;
  endTime?: string;
  topic: string;
  tags: number[];
  keywords?: string;
  audienceType: "ALL_USERS" | "SEGMENTED";
  weight: number;
  initialCtr: number;
  state: State;
  published: boolean;
  author: string;
  lastEditAuthor: string;
  places: number[];
}

export interface CampaignDetails extends Campaign {
  banners: Banner[];
  contents: Content[];
  creatives: Creative[];
  segments: { included: string[]; excluded: string[] };
}

export interface CampaignListItem {
  id: number; name: string; state: State; published: boolean; topic: string;
  startDate: string; startTime: string; endDate?: string; endTime?: string;
}

export interface ApiErrorItem { code: string; message: string; field?: string; hint?: string }

export interface Validation {
  errors: ApiErrorItem[];
  warnings: string[];
  warningDetails: ApiErrorItem[];
}

export interface AuditEntry {
  id: number; campaignId: number; entity: string; entityId: number; action: string;
  changes: Record<string, { from: unknown; to: unknown }> | null; at: string; actor: string; comment: string | null;
}

// --- справочники ---
export interface Topic { value: string; label: string }
export interface Tag { id: number; name: string }
export interface BannerType { id: number; code: string; description: string; previewForm: string; titleMaxLength: number; textMaxLength: number; channels: string[] }
export interface Segment { code: string; name: string; type: string; state: string; count: number }
export interface Place { id: number; code: string; description: string; defaultBanner: string | null; state: string }

export interface Dicts {
  topics: Topic[];
  tags: Tag[];
  bannerTypes: BannerType[];
  segments: Segment[];
  places: Place[];
}

// --- агент ---
export interface PlanStep {
  n: number;
  tool: string;
  summary: string;
  ref?: string | null;
  args: Record<string, unknown>;
  preview: { kind: string; [k: string]: unknown };
}

export interface PendingAction { id: string; title: string; created_at: string; steps: PlanStep[] }

export interface StepResult { step: number; summary: string; ok: boolean; id?: number | null; status?: number; errors?: ApiErrorItem[] }

export interface JournalEntry { at: string; actor: string; role: string; event: string; detail: unknown }

export interface AgentState {
  session_id: string;
  user: string;
  role: Role;
  reply: string;
  campaign_id: number | null;
  campaign?: CampaignDetails | null;
  validation?: Validation;
  pending_action: PendingAction | null;
  last_result: StepResult[];
  journal: JournalEntry[];
  awaiting_fix?: boolean;
  title?: string;
  suggestions?: string[];          // кнопки быстрых ответов под репликой ассистента
  recommendations?: Recommendation[];
  transcript?: TranscriptItem[];
}

// Лента диалога, которую хранит агент (для истории и восстановления после перезагрузки).
export interface TranscriptItem {
  kind: "user" | "assistant" | "result";
  text?: string;
  results?: StepResult[];
  rejected?: string;
  at: string;
}

export interface HistoryItem {
  id: string;
  title: string;
  updated_at: string;
  created_at: string;
  user: string;
  campaign_id: number | null;
  campaign_name?: string | null;
  messages: number;
  pending: boolean;
}

export interface ChatItem {
  kind: "user" | "assistant" | "result";
  text?: string;
  results?: StepResult[];
  rejected?: string;
}

// Статистика кампании (GET /campaigns/{id}/stats): факт для запущенных, прогноз для остальных.
export interface StatShare { key: string; label: string; share: number; count: number }
export interface StatDay { date: string; impressions: number; clicks: number; reach: number }
export interface CampaignStats {
  campaignId: number;
  mode: "fact" | "forecast";
  period: "day" | "week" | "month" | "all";
  granularity: "hour" | "day";
  from: string; to: string; days: number; totalDays: number;
  audienceSize: number; reach: number; impressions: number; clicks: number;
  ctr: number; frequency: number; conversions: number;
  daily: StatDay[];
  age: StatShare[]; gender: StatShare[]; cities: StatShare[]; platforms: StatShare[]; places: StatShare[];
  note: string;
}

// Рекомендация ассистента по текущей кампании: что сделать и почему; prompt — готовая просьба.
export interface Recommendation { id: string; title: string; why: string; prompt: string }
