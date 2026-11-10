export const HELP_ONBOARDING_PROMPT_EVENT = "chat:help-onboarding-prompt";

export interface HelpOnboardingPromptDetail {
  prompt: string;
}

export function dispatchHelpOnboardingPrompt(prompt: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<HelpOnboardingPromptDetail>(HELP_ONBOARDING_PROMPT_EVENT, {
      detail: { prompt },
    }),
  );
}
