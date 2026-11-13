import type { Metadata } from "next"
import Link from "next/link"
import { LegalPage } from "@/components/layout/legal-page"

export const metadata: Metadata = { title: "Privacy policy" }

export default function PrivacyPage() {
  return (
    <LegalPage title="Vesquiri privacy policy">
      <p>VisaAtlas Ltd operates Vesquiri and is responsible for the personal information described in this notice. This policy covers our website and Android and iOS apps. For privacy questions or requests, email <a href="mailto:visaatlasdigital@gmail.com">visaatlasdigital@gmail.com</a>.</p>
      <p>Only upload information you are authorised to use. Review your files before uploading and remove personal or confidential information that is not needed for your analysis.</p>

      <h2>Information we process</h2>
      <ul>
        <li><strong>Account information:</strong> your email address, account identifier and profile details you provide. If you choose Google sign-in, we receive the identity and profile information that Google shares with your permission. Authentication is handled by Supabase.</li>
        <li><strong>Your content:</strong> uploaded files, file names, descriptions, analysis instructions, questions, chat history, analysis results and links you choose to create.</li>
        <li><strong>Service information:</strong> usage counts, storage use, request and error records, and technical information needed to operate and secure the service. Hosting providers receive network information such as your IP address when you connect.</li>
        <li><strong>Support information:</strong> information you send when asking for help or exercising your rights.</li>
        <li><strong>Purchase information:</strong> the product, store, purchase status, access dates and purchase identifiers needed to verify paid access. We send an opaque Vesquiri account identifier to Apple or Google to link a purchase to your account. Google purchase tokens retained for verification are encrypted. We do not receive your full payment-card details from the stores.</li>
      </ul>
      <p>We do not require access to your contacts, precise device location, microphone or advertising identifier. Choose which files to upload using your device&apos;s file picker.</p>

      <h2>How we use information</h2>
      <p>We use account information and your content to provide the service you request: signing in, storing files, creating analyses, answering questions and exporting results. Our legal basis for this is performing our contract with you. Required account information is necessary to provide these features.</p>
      <p>We use service and support information to investigate problems, prevent abuse and keep the service reliable, based on our legitimate interests in operating a secure service. We may also process information to meet legal obligations. Where we rely on consent, you can withdraw it by contacting us; withdrawal does not affect earlier lawful processing.</p>
      <p>AI answers can be inaccurate. We do not use the app to make decisions about you that have legal or similarly significant effects.</p>

      <h2>AI processing and service providers</h2>
      <p>Vesquiri uses OpenAI for AI features. Depending on the feature, processing can include dataset labels and values, statistical summaries, file descriptions, instructions, questions and relevant conversation history. Do not include information you are not authorised to send for this processing.</p>
      <p>Supabase provides authentication. Railway hosts the service. Our infrastructure, database and error-monitoring providers process information needed to provide and maintain the service. Providers may process information outside the UK. Contact us for details of the locations and transfer safeguards applicable to your information.</p>
      <p>We do not sell your personal information or use it for advertising. We may disclose information when required by law or to protect the service and its users.</p>
      <p>Stripe processes website payments. Apple and Google process purchases made through their respective app stores and handle payment information under their own privacy policies. We check purchase status with the relevant provider to deliver access, process renewals and respond to refunds.</p>

      <h2>Sharing your analyses</h2>
      <p>Creating a share link makes that analysis accessible to anyone with the link. Only share information you are authorised to disclose. Other people may keep copies of content you share or export. Deleting your account cannot remove copies they have already saved.</p>

      <h2>Storage, retention and deletion</h2>
      <p>After account deletion, we retain a minimal purchase ownership record to prevent a receipt being reused by another account and to handle renewals, refunds and disputes. This does not recreate your deleted account. Store subscriptions must be cancelled in the store separately.</p>
      <p>We retain account information and saved content while your account is active and the information is needed to provide the service. You can delete individual analyses or request deletion of your entire account. Account deletion removes your login and associated uploads, analyses and chats from the active service. Technical or support records may be retained where needed for security, resolving disputes or legal obligations; any such exception is explained when handling your request.</p>
      <p>Service-provider backups may keep residual copies until those backups expire or are replaced. These are not used to restore a deleted account as an active account. Contact us for the retention details applicable to a particular record. See <Link href="/delete-account">account and data deletion</Link> for instructions, including requests without the app.</p>

      <h2>Cookies and device storage</h2>
      <p>The website uses authentication cookies and local storage to maintain your session and preferences. The mobile app stores authentication information on your device so you can stay signed in. Signing out removes the app&apos;s active session. We do not use advertising cookies.</p>

      <h2>Your choices and rights</h2>
      <p>Depending on applicable law, you can ask to access, correct, erase, restrict or transfer your personal information, or object to processing based on legitimate interests. Email the contact above. We may ask for proportionate information to verify that you own the account. Do not send your password. You can also complain to the UK <a href="https://ico.org.uk/make-a-complaint/">Information Commissioner&apos;s Office</a>.</p>
      <p>Vesquiri is intended for adults aged 18 and over. If you believe a child has provided personal information, contact us so we can investigate.</p>
      <h2>Changes to this policy</h2>
      <p>We will update this page when our practices change and communicate material changes through the service or your account email where appropriate.</p>
    </LegalPage>
  )
}
