import type { Metadata } from "next"
import Link from "next/link"
import { LegalPage } from "@/components/layout/legal-page"

export const metadata: Metadata = { title: "Terms of use" }

export default function TermsPage() {
  return (
    <LegalPage title="Vesquiri terms of use">
      <p>Vesquiri is a data-analysis service operated by VisaAtlas Ltd. Contact <a href="mailto:visaatlasdigital@gmail.com">visaatlasdigital@gmail.com</a> for support or questions about these terms.</p>
      <h2>Using the service</h2>
      <p>You must be at least 18 to use Vesquiri. Keep your sign-in details secure and provide accurate account information. Use the service lawfully and respect other people&apos;s rights. Do not attempt to access another account, disrupt the service or bypass usage limits.</p>
      <h2>Your data and content</h2>
      <p>You retain your rights in the content you upload. You authorise us and our service providers to process it to deliver the features you request. Only upload data you are authorised to use and send for AI processing. Our <Link href="/privacy">privacy policy</Link> explains that processing.</p>
      <p>When you create a public analysis link, anyone with the link can view the analysis. Review your content before sharing it.</p>
      <h2>Analyses and AI answers</h2>
      <p>Outputs depend on the quality and completeness of the data you provide. AI-generated explanations may be wrong or incomplete. Check results against your original records before acting. Vesquiri does not provide professional financial, legal or medical advice.</p>
      <h2>Closed testing</h2>
      <p>The current test build connects to staging. Features and availability may change, and test data may be reset. Use sample data and keep your own copies of important files. The mobile test build does not offer in-app purchases.</p>
      <h2>Ending use</h2>
      <p>You can stop using Vesquiri at any time and <Link href="/delete-account">delete your account</Link>. We may restrict access where necessary to prevent abuse or meet legal obligations. Nothing in these terms excludes rights or remedies that cannot lawfully be excluded, including applicable consumer rights.</p>
      <h2>Changes</h2>
      <p>We may update these terms as the service develops. Material changes will be communicated through the service or your account email where appropriate.</p>
    </LegalPage>
  )
}
