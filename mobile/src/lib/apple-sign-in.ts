type AppleCredential = { identityToken: string | null; state: string | null };

/** Keep the nonce private to this attempt. Apple receives its SHA-256 digest. */
export async function performAppleSignIn(deps: {
  random: () => string;
  sha256: (value: string) => Promise<string>;
  authorize: (nonce: string, state: string) => Promise<AppleCredential>;
  exchange: (token: string, nonce: string) => Promise<{ error: unknown }>;
}) {
  const nonce = deps.random();
  const state = deps.random();
  const credential = await deps.authorize(await deps.sha256(nonce), state);
  if (credential.state !== state) throw new Error('Apple sign-in could not be verified. Please try again.');
  if (!credential.identityToken) throw new Error('Apple did not return a sign-in token. Please try again.');
  const result = await deps.exchange(credential.identityToken, nonce);
  if (result.error) throw result.error;
}
