import type { Metadata } from "next"
import Link from "next/link"
import { LegalPage } from "@/components/layout/legal-page"

export const metadata: Metadata = { title: "Account and data deletion" }

export default function DeleteAccountPage() {
  return (
    <LegalPage title="Delete your Vesquiri account and data">
      <p>Vesquiri is operated by VisaAtlas Ltd. You can request deletion without reinstalling the app or signing in.</p>
      <h2>Delete from the mobile app</h2>
      <ol>
        <li>Open Vesquiri and sign in to your account.</li>
        <li>Open Settings, then choose <strong>Delete my account</strong>.</li>
        <li>Read the confirmation and select <strong>Delete account</strong>. This is permanent.</li>
      </ol>
      <p>Wait for any running analyses to finish before deleting. If deletion fails, retry or use the email method below.</p>
      <h2>Request deletion without the app</h2>
      <p>Email <a href="mailto:visaatlasdigital@gmail.com?subject=Vesquiri%20account%20deletion%20request">visaatlasdigital@gmail.com</a> from your account email address with the subject <strong>Vesquiri account deletion request</strong>. Tell us that you want your account and associated data deleted. If you no longer have access to that email address, explain this so we can help verify ownership. Never send your password.</p>
      <p>We will verify your ownership, process the request and confirm the outcome. If additional information or a retention exception is necessary, we will explain it. Requests under UK data-protection law are normally answered within one month.</p>
      <h2>What is deleted</h2>
      <p>Deletion removes your login, profile, uploaded files, analyses and chat history from the active service. Shared analysis links stop working when the associated analysis is removed. Copies already exported or saved by other people are outside our control.</p>
      <p>Limited security, support or legally required records may need to be retained. Residual copies in provider backups remain until those backups expire or are replaced. We explain any applicable exceptions when handling your request.</p>
      <h2>Delete some data while keeping your account</h2>
      <p>Open an analysis and choose <strong>Delete analysis</strong> to remove that analysis and its chat history. To request removal of an uploaded file or other specific information while keeping your account, email the address above with the subject <strong>Vesquiri data deletion request</strong> and identify the information. See our <Link href="/privacy">privacy policy</Link> for more details.</p>
    </LegalPage>
  )
}
