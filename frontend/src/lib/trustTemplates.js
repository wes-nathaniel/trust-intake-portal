/**
 * Boilerplate clauses for the Two-Panel Trust Viewer.
 * Each template provides BOTH a legal `trust_html` block (left panel)
 * AND a plain-English `explain_html` (right panel).
 *
 * Used by the RichTextEditor "Insert template" dropdown — selecting a
 * template inserts the appropriate variant at the current cursor position
 * via document.execCommand("insertHTML").
 *
 * The HTML uses ONLY tags supported by RichTextEditor's prose styles:
 *   p, h3, ul, ol, li, strong, em, u, blockquote, a
 */
export const TRUST_TEMPLATES = [
  {
    key: "revocation",
    title: "Revocation",
    trust_html: `<h3>Revocation, Amendment, and Modification</h3>
<p>The Grantor reserves the right, at any time and from time to time during the Grantor&rsquo;s lifetime, by an instrument in writing signed by the Grantor and delivered to the Trustee, to <strong>revoke</strong> this Trust in whole or in part, or to <strong>amend</strong> any provision of this Trust.</p>
<p>Upon revocation, the Trustee shall deliver to the Grantor all property then held in the Trust, together with any undistributed income. The power to revoke or amend this Trust is personal to the Grantor and may not be exercised by any agent, conservator, or other representative except as expressly authorized in writing.</p>`,
    explain_html: `<p>You — the person creating this trust — can <strong>change your mind</strong> at any time while you are alive and mentally able.</p>
<ul>
  <li>You can <em>cancel</em> the entire trust and take your assets back.</li>
  <li>You can <em>edit</em> any part of it (beneficiaries, trustees, distribution rules).</li>
  <li>You must put the change in writing and sign it.</li>
</ul>
<p>Only <strong>you</strong> can do this — not a family member, not a power-of-attorney agent (unless you specifically grant that power in writing).</p>`,
  },
  {
    key: "successor-trustee",
    title: "Successor Trustee",
    trust_html: `<h3>Successor Trustees</h3>
<p>Upon the death, resignation, incapacity, or removal of the initial Trustee, the following individuals shall serve as Successor Trustee, in the order listed:</p>
<ol>
  <li><strong>[Successor Trustee #1 — Full Legal Name]</strong></li>
  <li><strong>[Successor Trustee #2 — Full Legal Name]</strong></li>
  <li><strong>[Corporate Trustee or other backup]</strong></li>
</ol>
<p>A Successor Trustee shall be deemed incapacitated upon written certification by two licensed physicians that such Trustee is unable to manage his or her own financial affairs. Each Successor Trustee shall serve without bond and shall have all powers granted to the original Trustee under this Trust.</p>`,
    explain_html: `<p>If your first-choice trustee can&rsquo;t serve — because they pass away, step down, become unable to manage things, or are removed — this section names <strong>who takes over next</strong>, in order.</p>
<ul>
  <li>Your <strong>1st backup</strong> serves first.</li>
  <li>If the 1st backup can&rsquo;t serve, the <strong>2nd backup</strong> steps in.</li>
  <li>And so on down the list.</li>
</ul>
<p>To declare a trustee mentally incapable, <strong>two licensed doctors</strong> must agree in writing. None of these backups have to post a bond (no insurance deposit), which keeps administration simple and cheap.</p>`,
  },
  {
    key: "spendthrift",
    title: "Spendthrift",
    trust_html: `<h3>Spendthrift Provision</h3>
<p>No interest of any beneficiary in the income or principal of this Trust shall be subject to <strong>assignment, alienation, pledge, attachment, or claims of creditors</strong> of such beneficiary, including claims for alimony or separate maintenance, nor shall such interest be subject to the beneficiary&rsquo;s voluntary or involuntary transfer.</p>
<p>The Trustee may, in the Trustee&rsquo;s sole and absolute discretion, withhold any distribution from a beneficiary whose interest would otherwise be subject to such claim, and may instead apply such amounts directly for the beneficiary&rsquo;s health, education, maintenance, or support.</p>`,
    explain_html: `<p>This is a <strong>shield</strong> that protects your beneficiaries&rsquo; inheritance.</p>
<ul>
  <li>If a beneficiary gets <em>sued</em>, files for <em>bankruptcy</em>, or goes through a <em>divorce</em>, creditors and ex-spouses generally <strong>cannot reach</strong> the trust money.</li>
  <li>Beneficiaries also <strong>cannot pre-spend</strong> their inheritance by borrowing against it or selling their future share.</li>
</ul>
<p>If a beneficiary is in trouble, the trustee can pay <em>directly</em> for things like rent, tuition, or medical bills — instead of handing cash that creditors could grab.</p>`,
  },
  {
    key: "no-contest",
    title: "No Contest",
    trust_html: `<h3>No-Contest (In Terrorem) Clause</h3>
<p>If any beneficiary of this Trust, alone or in conjunction with any other person, directly or indirectly <strong>contests, disputes, or attacks the validity</strong> of this Trust, or any provision hereof, or institutes or aids in the institution of any legal proceeding to set aside, invalidate, or modify any of its terms, then any share, interest, or distribution otherwise passing to such beneficiary under this Trust shall be <strong>revoked</strong>, and such beneficiary shall be treated for all purposes as having predeceased the Grantor without surviving descendants.</p>
<p>This clause shall not apply to a good-faith proceeding brought solely to construe ambiguous terms of this Trust.</p>`,
    explain_html: `<p>This is a <strong>&ldquo;don&rsquo;t fight the trust&rdquo;</strong> rule.</p>
<ul>
  <li>If a beneficiary <em>sues</em> to overturn the trust or get more than what you left them, they lose <strong>their entire inheritance</strong>.</li>
  <li>They&rsquo;re treated as if they died before you — so their share goes to whoever was next in line.</li>
</ul>
<p>It does <strong>not</strong> punish someone for asking a court a legitimate question — for example, &ldquo;What did this paragraph mean?&rdquo; It only kicks in for an actual attack on the trust itself.</p>`,
  },
  {
    key: "powers-of-trustee",
    title: "Powers of Trustee",
    trust_html: `<h3>Powers of the Trustee</h3>
<p>In addition to all powers conferred upon trustees by applicable state law, the Trustee shall have the following powers, exercisable in the Trustee&rsquo;s sole discretion and without court order:</p>
<ol>
  <li>To <strong>retain, sell, exchange, lease, mortgage, or otherwise dispose of</strong> any property of the Trust, real or personal, on such terms as the Trustee deems advisable;</li>
  <li>To <strong>invest and reinvest</strong> Trust assets in any kind of property, including stocks, bonds, mutual funds, real estate, or business interests, without being limited by any statute governing trustee investments;</li>
  <li>To <strong>borrow money</strong> and to pledge or mortgage Trust property as security;</li>
  <li>To <strong>employ attorneys, accountants, investment advisors, and other professionals</strong>, and to pay their reasonable fees from the Trust;</li>
  <li>To <strong>distribute Trust property in cash or in kind</strong>, or partly in each, and to allocate property non-pro-rata among beneficiaries;</li>
  <li>To <strong>compromise, settle, or abandon claims</strong> in favor of or against the Trust.</li>
</ol>`,
    explain_html: `<p>This section gives the trustee a <strong>broad toolkit</strong> to manage your assets the same way you would.</p>
<ul>
  <li><strong>Buy, sell, rent, or borrow against</strong> any trust property.</li>
  <li><strong>Invest</strong> in stocks, bonds, real estate, or businesses — without being limited to ultra-conservative options.</li>
  <li><strong>Hire experts</strong> (lawyers, CPAs, financial advisors) and pay them from trust funds.</li>
  <li><strong>Distribute</strong> assets as cash or as the actual property (a house, jewelry, a car) — and split things unevenly when that&rsquo;s smarter.</li>
  <li><strong>Settle lawsuits</strong> on the trust&rsquo;s behalf.</li>
</ul>
<p>The point is to keep things <strong>moving</strong> without having to ask a judge for permission every time.</p>`,
  },
  {
    key: "distribution-to-beneficiaries",
    title: "Distribution to Beneficiaries",
    trust_html: `<h3>Distribution to Beneficiaries</h3>
<p>Upon the death of the Grantor, after payment of all valid debts, expenses of last illness, funeral expenses, and administration costs, the Trustee shall distribute the remaining Trust estate as follows:</p>
<ol>
  <li>To <strong>[Primary Beneficiary — Full Legal Name]</strong>, <strong>[percentage or specific property]</strong>;</li>
  <li>To <strong>[Secondary Beneficiary — Full Legal Name]</strong>, <strong>[percentage or specific property]</strong>;</li>
  <li>The remainder, in equal shares <em>per stirpes</em>, to the Grantor&rsquo;s then-living descendants.</li>
</ol>
<p>If any beneficiary is under the age of <strong>twenty-five (25)</strong> at the time of distribution, the Trustee shall hold such beneficiary&rsquo;s share in a separate sub-trust and shall distribute income and principal as needed for the beneficiary&rsquo;s health, education, maintenance, and support until the beneficiary attains the stated age, whereupon any remaining balance shall be distributed outright.</p>`,
    explain_html: `<p>This section explains <strong>who gets what</strong> after you pass away.</p>
<ul>
  <li>First, the trustee pays off any final bills (medical, funeral, administrative).</li>
  <li>Then your beneficiaries receive their shares in the order and percentages you set.</li>
  <li>If a beneficiary has already passed, their share goes to <em>their</em> children (this is what <em>&ldquo;per stirpes&rdquo;</em> means).</li>
</ul>
<p><strong>For young beneficiaries:</strong> if anyone is under <strong>25</strong>, the trustee holds their share and pays for their living expenses, school, and health needs — instead of handing over a large lump sum. When they turn 25, they get whatever is left.</p>`,
  },
];
