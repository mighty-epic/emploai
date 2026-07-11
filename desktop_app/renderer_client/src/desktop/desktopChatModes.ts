import type { DesktopMessage } from './desktopMessages';

export type PlanQuestionOption = {
  id: string;
  label: string;
  description?: string;
};

export type PlanQuestionCard = {
  question_id: string;
  header?: string;
  question: string;
  options: PlanQuestionOption[];
};

export function extractProposedPlan(content: string) {
  const match = String(content || '').match(/<proposed_plan>\s*([\s\S]*?)\s*<\/proposed_plan>/i);
  return match?.[1]?.trim() || null;
}

export function visiblePlanText(content: string) {
  const plan = extractProposedPlan(content);
  if (!plan) {
    return content;
  }
  return String(content || '').replace(/<proposed_plan>[\s\S]*?<\/proposed_plan>/i, '').trim();
}

export function planQuestionFromMessage(message: DesktopMessage): PlanQuestionCard | null {
  const metadata = (message.raw?.metadata || {}) as Record<string, any>;
  const question = metadata.plan_question || (message.raw as any)?.plan_question;
  if (!question || typeof question !== 'object') {
    return null;
  }
  const questionId = String(question.question_id || '').trim();
  const questionText = String(question.question || message.content || '').trim();
  const options = Array.isArray(question.options)
    ? question.options
        .map((option: any, index: number) => ({
          id: String(option?.id || `option_${index + 1}`),
          label: String(option?.label || '').trim(),
          description: String(option?.description || '').trim(),
        }))
        .filter((option: PlanQuestionOption) => option.label)
    : [];
  if (!questionId || !questionText || options.length < 1) {
    return null;
  }
  return {
    question_id: questionId,
    header: String(question.header || 'Plan').trim(),
    question: questionText,
    options,
  };
}

export function modeStatusLabel(planMode: Record<string, any> | null | undefined) {
  const status = String(planMode?.status || '').trim().replace(/_/g, ' ');
  return status || 'active';
}
