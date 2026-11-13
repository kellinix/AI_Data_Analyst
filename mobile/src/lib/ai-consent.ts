export function requireAiConsent(accepted: boolean) {
  if (!accepted) throw new Error('Please choose whether to share data with OpenAI before using AI analysis.');
}
