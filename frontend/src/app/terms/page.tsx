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
      <h2>Mobile closed testing</h2>
      <p>Mobile test builds may change as testing progresses. Use sample data and keep your own copies of important files. Purchase options are shown only in builds and stores where they are enabled.</p>
      <h2>Web purchases</h2>
      <p>Where checkout is enabled, Pro is available for £19 per month, renewing until you cancel, or £5.99 once for seven days from successful payment. The seven-day pass does not renew. Both options use the published Pro allowances; buying does not reset your existing monthly usage counts. After paid access ends, Free allowances apply. We do not delete saved files just because a pass expires, but you may need to remove files before uploading more.</p>
      <p>Stripe processes web payments. Confirm the amount and whether it renews before paying. Manage recurring billing and cancel it through Settings. Period-end cancellation keeps access until the end of the paid period. Contact us about billing problems, refunds or your applicable cancellation rights. A full refund or disputed payment can end the access provided by a one-time pass. Your statutory consumer rights are unaffected.</p>
      <h2>App Store and Google Play purchases</h2>
      <p>Where available, purchases made inside the iOS or Android app are processed by Apple or Google. The app displays your store&apos;s localized price before purchase. Monthly Pro renews automatically until cancelled in your store account. The seven-day pass is one payment for seven days and does not renew automatically. Both use the same published calendar-month Pro allowances; a purchase or renewal does not reset usage.</p>
      <p>Sign in to the Vesquiri account you want to use before buying. Verified access works across devices when you use that account. Use Restore purchases to check store purchases again. Manage subscriptions and cancellation through the store where you subscribed, and use that store&apos;s refund process. Deleting Vesquiri or your Vesquiri account does not cancel an Apple or Google subscription. Store refunds or revocation can end the access provided by that purchase. Your statutory consumer rights are unaffected.</p>
      <h2>Ending use</h2>
      <p>You can stop using Vesquiri at any time and <Link href="/delete-account">delete your account</Link>. We may restrict access where necessary to prevent abuse or meet legal obligations. Nothing in these terms excludes rights or remedies that cannot lawfully be excluded, including applicable consumer rights.</p>
      <h2>Changes</h2>
      <p>We may update these terms as the service develops. Material changes will be communicated through the service or your account email where appropriate.</p>
    </LegalPage>
  )
}
