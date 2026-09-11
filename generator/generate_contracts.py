"""Generate 20 synthetic ISDA 2002 Master Agreements as text-embedded PDFs.

Structure per document (mirrors a real executed ISDA package):
  1. Cover page
  2. Printed Master Agreement (Sections 1-14) - identical boilerplate
  3. Schedule (Parts 1-5) - party-specific, negotiated elections
  4. Credit Support Annex - party-specific thresholds

The boilerplate is standard, publicly-published ISDA 2002 language, lightly
condensed. The searchable variation lives in the Schedule and CSA and in the
counterparty metadata (counterparties.py).

Also writes contracts/manifest.json with per-document metadata for ingestion.
"""
import json
import os
from datetime import date

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak)

from counterparties import PARTY_A, COUNTERPARTIES

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "contracts")
os.makedirs(OUT_DIR, exist_ok=True)

styles = getSampleStyleSheet()
H_TITLE = ParagraphStyle("t", parent=styles["Title"], fontSize=18, leading=22,
                         alignment=TA_CENTER, spaceAfter=14)
H_SUB = ParagraphStyle("s", parent=styles["Heading2"], fontSize=12, leading=15,
                       alignment=TA_CENTER, spaceAfter=8)
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=13, leading=16,
                    spaceBefore=12, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, leading=14,
                    spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("b", parent=styles["BodyText"], fontSize=9.5, leading=13,
                      alignment=TA_JUSTIFY, spaceAfter=6)
COVER = ParagraphStyle("c", parent=styles["BodyText"], fontSize=11, leading=16,
                       alignment=TA_CENTER, spaceAfter=6)


def P(text, style=BODY):
    return Paragraph(text, style)


# ---------------------------------------------------------------------------
# Printed ISDA 2002 Master Agreement boilerplate (Sections 1-14, condensed).
# Identical across all agreements, as in real executed packages.
# ---------------------------------------------------------------------------
MASTER_SECTIONS = [
    ("1. Interpretation",
     "(a) Definitions. The terms defined in Section 14 and elsewhere in this "
     "Master Agreement will have the meanings therein specified for the purpose "
     "of this Master Agreement. (b) Inconsistency. In the event of any "
     "inconsistency between the provisions of the Schedule and the other "
     "provisions of this Master Agreement, the Schedule will prevail. In the "
     "event of any inconsistency between the provisions of any Confirmation and "
     "this Master Agreement, such Confirmation will prevail for the purpose of "
     "the relevant Transaction. (c) Single Agreement. All Transactions are "
     "entered into in reliance on the fact that this Master Agreement and all "
     "Confirmations form a single agreement between the parties, and the parties "
     "would not otherwise enter into any Transactions."),
    ("2. Obligations",
     "(a) General Conditions. Each party will make each payment or delivery "
     "specified in each Confirmation to be made by it, subject to the other "
     "provisions of this Agreement. Payments under this Agreement will be made "
     "on the due date for value on that date in the place of the account "
     "specified in the relevant Confirmation, in freely transferable funds. "
     "(c) Netting of Payments. If on any date amounts would otherwise be payable "
     "in the same currency and in respect of the same Transaction by each party "
     "to the other, then such amounts will be aggregated and the party owing the "
     "larger amount will pay the excess. Multiple Transaction Payment Netting "
     "applies as specified in the Schedule. (d) Deduction or Withholding for Tax. "
     "All payments will be made without withholding or deduction for Tax unless "
     "required by law, in which case the payer shall pay such additional amounts "
     "(gross-up) as set out in this Section, subject to the exceptions for "
     "Indemnifiable Tax."),
    ("3. Representations",
     "Each party makes the representations contained in Section 3(a) (Basic "
     "Representations), including status, powers, no violation or conflict, "
     "consents and obligations binding; Section 3(b) Absence of Certain Events; "
     "Section 3(c) Absence of Litigation; Section 3(d) Accuracy of Specified "
     "Information; Section 3(e) Payer Tax Representation; Section 3(f) Payee Tax "
     "Representations; and Section 3(g) No Agency. Additional representations, if "
     "any, are specified in Part 5 of the Schedule."),
    ("4. Agreements",
     "Each party agrees to furnish specified information and any documents "
     "specified in the Schedule (including tax forms); to use reasonable efforts "
     "to maintain authorisations and comply with applicable laws; to give notice "
     "of any Event of Default or Potential Event of Default; and to comply with "
     "the tax agreements set out in this Section."),
    ("5. Events of Default and Termination Events",
     "(a) Events of Default. The occurrence of any of the following constitutes "
     "an Event of Default with respect to a party: (i) Failure to Pay or Deliver; "
     "(ii) Breach of Agreement; Repudiation of Agreement; (iii) Credit Support "
     "Default; (iv) Misrepresentation; (v) Default under Specified Transaction; "
     "(vi) Cross-Default (if specified as applying in the Schedule), meaning the "
     "occurrence of a default in respect of Specified Indebtedness in an "
     "aggregate amount not less than the applicable Threshold Amount; (vii) "
     "Bankruptcy; and (viii) Merger Without Assumption. (b) Termination Events. "
     "The occurrence of any of the following constitutes a Termination Event: "
     "(i) Illegality; (ii) Force Majeure Event; (iii) Tax Event; (iv) Tax Event "
     "Upon Merger; and, if specified in the Schedule, (v) Credit Event Upon "
     "Merger and (vi) Additional Termination Event. (d) Deferral of Payments and "
     "Deliveries During a Waiting Period applies in respect of Illegality and "
     "Force Majeure Event."),
    ("6. Early Termination; Close-out Netting",
     "(a) Right to Terminate Following Event of Default. If at any time an Event "
     "of Default has occurred and is then continuing, the Non-defaulting Party "
     "may, by not more than 20 days notice, designate an Early Termination Date "
     "in respect of all outstanding Transactions. (b) Right to Terminate "
     "Following Termination Event. If a Termination Event occurs, an Affected "
     "Party will notify the other and the parties will follow the transfer / "
     "close-out procedure. (a) Automatic Early Termination. If specified in the "
     "Schedule as applying, then certain Bankruptcy Events of Default will "
     "automatically constitute an Early Termination Date. (e) Payments on Early "
     "Termination. The amount payable will be determined using the Close-out "
     "Amount and the Payment Measure elected in the Schedule, and will be paid in "
     "the Termination Currency. Set-off applies as specified in the Schedule."),
    ("7. Transfer",
     "Subject to the Credit Support Documents and except as provided in Section "
     "6(b)(ii), neither party may transfer any interest or obligation under this "
     "Agreement without the prior written consent of the other party, except "
     "pursuant to a consolidation, amalgamation, merger, or transfer of all or "
     "substantially all its assets to another entity."),
    ("8. Contractual Currency",
     "Each payment under this Agreement will be made in the relevant currency "
     "specified for that payment (the Contractual Currency). To the extent "
     "permitted by law, any obligation to make payments in the Contractual "
     "Currency will not be discharged by payment in another currency except to "
     "the extent the recipient may purchase the Contractual Currency."),
    ("9. Miscellaneous",
     "(a) Entire Agreement. This Agreement constitutes the entire agreement of "
     "the parties. (b) Amendments must be in writing. (e) Counterparts. This "
     "Agreement may be executed in counterparts, each of which is an original. "
     "(h) Interest and Compensation is payable on defaulted and deferred amounts "
     "at the Default Rate or the Applicable Deferral Rate as provided herein."),
    ("10. Offices; Multibranch Parties",
     "Each party that enters into a Transaction through an Office other than its "
     "head or home office represents that its obligations are the same as if it "
     "had entered into the Transaction through its head or home office. A party "
     "is a Multibranch Party if so specified in Part 4 of the Schedule and may "
     "act through any of the Offices listed there."),
    ("11. Expenses",
     "A Defaulting Party will, on demand, indemnify and hold harmless the other "
     "party for and against all reasonable out-of-pocket expenses, including "
     "legal fees and Stamp Tax, incurred by reason of the enforcement and "
     "protection of its rights under this Agreement."),
    ("12. Notices",
     "Any notice or communication in respect of this Agreement will be effective "
     "if in writing and delivered in person, by courier, by certified mail, or "
     "by electronic messaging system or e-mail to the address specified in Part "
     "4 of the Schedule. A notice designating an Early Termination Date may not "
     "be given by electronic messaging system or e-mail."),
    ("13. Governing Law and Jurisdiction",
     "(a) Governing Law. This Agreement will be governed by and construed in "
     "accordance with the law specified in the Schedule. (b) Jurisdiction. Each "
     "party submits to the jurisdiction of the courts specified in the Schedule. "
     "(c) Service of Process. Each party appoints the Process Agent (if any) "
     "specified in Part 4 of the Schedule. (d) Waiver of Immunities."),
    ("14. Definitions",
     "As used in this Agreement: Affiliate; Close-out Amount; Confirmation; "
     "Credit Support Document; Credit Support Provider; Cross-Default; Default "
     "Rate; Early Termination Date; Event of Default; Illegality; Force Majeure "
     "Event; Multiple Transaction Payment Netting; Non-defaulting Party; Office; "
     "Specified Entity; Specified Indebtedness; Specified Transaction; Tax; "
     "Termination Currency; Threshold Amount; and other terms have the meanings "
     "given in this Section 14 and the 2006 ISDA Definitions as incorporated."),
]


def build_story(cp):
    a, b = PARTY_A, cp
    eff = date.fromisoformat(cp["effective"])
    eff_str = eff.strftime("%d %B %Y")
    story = []

    # --- Cover page ---
    story += [Spacer(1, 1.2 * inch),
              P("ISDA&reg;", H_SUB),
              P("International Swaps and Derivatives Association, Inc.", COVER),
              Spacer(1, 0.3 * inch),
              P("2002 MASTER AGREEMENT", H_TITLE),
              Spacer(1, 0.2 * inch),
              P("dated as of " + eff_str, COVER),
              Spacer(1, 0.4 * inch),
              P("between", COVER),
              P("<b>%s</b>" % a["name"], COVER),
              P('("Party A")', COVER),
              P("and", COVER),
              P("<b>%s</b>" % b["name"], COVER),
              P('("Party B")', COVER),
              Spacer(1, 0.5 * inch),
              P("Document ID: %s &nbsp;|&nbsp; Counterparty: %s &nbsp;|&nbsp; "
                "LEI: %s" % (cp["id"], cp["short"], cp["lei"]), COVER),
              P("Governing Law: %s Law &nbsp;|&nbsp; Base Currency: %s"
                % (cp["governing_law"], cp["base_ccy"]), COVER),
              PageBreak()]

    # --- Preamble ---
    story += [P("PREAMBLE", H1),
              P("This 2002 Master Agreement (this &ldquo;Agreement&rdquo;) is made "
                "as of %s between <b>%s</b>, a company organised under the laws of "
                "%s (&ldquo;Party A&rdquo;), and <b>%s</b>, a %s organised under "
                "the laws of %s (&ldquo;Party B&rdquo;). The parties have entered "
                "and/or anticipate entering into one or more transactions "
                "(each a &ldquo;Transaction&rdquo;) that are or will be governed "
                "by this Master Agreement, which includes the schedule (the "
                "&ldquo;Schedule&rdquo;), and the documents and other confirming "
                "evidence (each a &ldquo;Confirmation&rdquo;) exchanged between "
                "the parties confirming those Transactions."
                % (eff_str, a["name"], a["jurisdiction"], b["name"],
                   b["type"].lower(), b["jurisdiction"]))]

    # --- Master body ---
    story += [P("PRINTED FORM &mdash; 2002 ISDA MASTER AGREEMENT", H1)]
    for title, text in MASTER_SECTIONS:
        story += [P(title, H2), P(text)]

    # --- Schedule ---
    story += [PageBreak(),
              P("SCHEDULE to the 2002 Master Agreement", H1),
              P("dated as of %s between %s (&ldquo;Party A&rdquo;) and %s "
                "(&ldquo;Party B&rdquo;)" % (eff_str, a["name"], b["name"]))]

    story += [P("Part 1. Termination Provisions", H2)]
    story += [P("(a) &ldquo;Specified Entity&rdquo; means, in relation to Party B "
                "for all purposes, <b>%s</b>. In relation to Party A, none is "
                "specified." % cp["specified_entity"])]
    story += [P("(b) &ldquo;Specified Transaction&rdquo; will have the meaning "
                "specified in Section 14 and shall include, without limitation, "
                "the following product types transacted between the parties: "
                "<b>%s</b>." % ", ".join(cp["products"]))]
    story += [P("(c) The &ldquo;Cross-Default&rdquo; provisions of Section "
                "5(a)(vi) <b>will apply</b> to Party A and Party B. "
                "&ldquo;Specified Indebtedness&rdquo; has the meaning specified in "
                "Section 14. &ldquo;Threshold Amount&rdquo; means, with respect to "
                "each party, <b>%s</b> (or its equivalent in any other currency)."
                % cp["cross_default"])]
    aet_txt = ("<b>will apply</b> to Party B and will not apply to Party A"
               if cp["aet"] else "<b>will not apply</b> to either party")
    story += [P("(d) The &ldquo;Automatic Early Termination&rdquo; provision of "
                "Section 6(a) %s." % aet_txt)]
    story += [P("(e) &ldquo;Termination Currency&rdquo; means <b>%s</b>."
                % cp["base_ccy"])]
    ate_items = "; ".join(cp["ate"])
    story += [P("(f) &ldquo;Additional Termination Event&rdquo; <b>will apply</b>. "
                "The following shall each constitute an Additional Termination "
                "Event with respect to Party B (the Affected Party): <b>%s</b>."
                % ate_items)]

    story += [P("Part 2. Tax Representations", H2),
              P("(a) Payer Tax Representations. For the purpose of Section 3(e), "
                "each of Party A and Party B makes the standard Payer Tax "
                "Representation. (b) Payee Tax Representations. For the purpose of "
                "Section 3(f), each party makes the representations appropriate to "
                "its jurisdiction of organisation (%s for Party B)."
                % cp["jurisdiction"])]

    story += [P("Part 3. Agreement to Deliver Documents", H2),
              P("Each party agrees to deliver, upon execution and upon request, "
                "the following documents: (i) an incumbency certificate and "
                "evidence of authority; (ii) an executed U.S. Internal Revenue "
                "Service Form W-9 or W-8BEN-E (as applicable); (iii) its most "
                "recent audited annual financial statements; and (iv) a legal "
                "opinion reasonably satisfactory to the other party. Party B's LEI "
                "is %s." % cp["lei"])]

    story += [P("Part 4. Miscellaneous", H2),
              P("(a) Addresses for Notices. Party A: %s Office, attention Legal "
                "Department, Derivatives Documentation. Party B: %s Office, "
                "attention ISDA Documentation Unit. (b) Process Agent. Party B "
                "appoints a Process Agent in the jurisdiction of the governing "
                "law where required. (c) Offices; Multibranch Party. Party B %s a "
                "Multibranch Party. (d) Calculation Agent: Party A, unless "
                "otherwise agreed in a Confirmation. (e) Credit Support Document: "
                "in relation to Party B, the %s. (f) Credit Support Provider: %s. "
                "(g) Governing Law: this Agreement will be governed by and "
                "construed in accordance with <b>%s law</b>. (h) Netting of "
                "Payments: Multiple Transaction Payment Netting applies to all "
                "Transactions."
                % (a["office"], b["office"],
                   "is" if b["type"] == "Dealer" else "is not",
                   cp["csa_type"], cp["specified_entity"], cp["governing_law"]))]

    story += [P("Part 5. Other Provisions", H2),
              P("(a) ISDA Definitions. The 2006 ISDA Definitions are incorporated "
                "into each Confirmation. (b) Relationship Between Parties. Each "
                "party represents non-reliance, that it is acting as principal, "
                "and that it has the capacity to evaluate and understand the "
                "Transaction. (c) Set-off. Upon the occurrence of an Early "
                "Termination Date, the Non-defaulting Party may set off any Early "
                "Termination Amount against any other amounts owing between the "
                "parties. (d) 2013 ISDA EMIR / Dodd-Frank Protocol provisions and "
                "the applicable Regulatory Margin Requirements are incorporated by "
                "reference. (e) Bail-in Acknowledgement: to the extent Party B is "
                "an EEA or UK financial institution, the parties acknowledge the "
                "contractual recognition of bail-in under Article 55 BRRD.")]

    # --- Credit Support Annex ---
    story += [PageBreak(),
              P("CREDIT SUPPORT ANNEX", H1),
              P("%s &mdash; Paragraph 11 Elections" % cp["csa_type"], H2),
              P("This Credit Support Annex supplements, forms part of, and is "
                "subject to the 2002 Master Agreement dated as of %s between %s "
                "and %s." % (eff_str, a["name"], b["name"]))]
    story += [P("(a) Base Currency and Eligible Currency. &ldquo;Base "
                "Currency&rdquo; means <b>%s</b>. (b) Credit Support Obligations. "
                "&ldquo;Delivery Amount&rdquo; and &ldquo;Return Amount&rdquo; "
                "have the meanings in Paragraph 3." % cp["base_ccy"])]
    story += [P("(c) Thresholds. &ldquo;Independent Amount&rdquo; means with "
                "respect to Party B: <b>%s</b>. &ldquo;Threshold&rdquo; means with "
                "respect to Party B: <b>%s</b>. &ldquo;Minimum Transfer "
                "Amount&rdquo; means with respect to each party: <b>%s</b>. "
                "Rounding: Delivery and Return Amounts will be rounded up and down "
                "respectively to the nearest integral multiple of 10,000 units of "
                "the Base Currency." % (cp["independent_amount"], cp["threshold"],
                                        cp["mta"]))]
    story += [P("(d) Eligible Collateral. Cash in the Base Currency (Valuation "
                "Percentage 100%); negotiable debt obligations issued by the U.S. "
                "Treasury with a remaining maturity of not more than one year "
                "(Valuation Percentage 99.5%), one to ten years (98%), and over "
                "ten years (96%). (e) Valuation and Timing. Valuation Agent: Party "
                "A. Valuation Date: each Local Business Day. Notification Time: "
                "1:00 p.m. on the Local Business Day. (f) Dispute Resolution: as "
                "per Paragraph 5. (g) Holding and Using Posted Collateral; "
                "Custodian; Interest Rate on cash equal to the relevant overnight "
                "risk-free rate (SOFR for USD; &euro;STR for EUR; SONIA for GBP).")]

    return story


def main():
    manifest = []
    for cp in COUNTERPARTIES:
        fname = "%s_%s_ISDA_2002_Master_Agreement.pdf" % (
            cp["id"], cp["short"].replace(" ", "_"))
        path = os.path.join(OUT_DIR, fname)
        doc = SimpleDocTemplate(path, pagesize=LETTER,
                                topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                                leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                                title="ISDA 2002 Master Agreement - %s" % cp["short"],
                                author=PARTY_A["name"])
        doc.build(build_story(cp))
        size = os.path.getsize(path)
        manifest.append({
            "doc_id": cp["id"],
            "file_name": fname,
            "counterparty": cp["name"],
            "counterparty_short": cp["short"],
            "counterparty_type": cp["type"],
            "jurisdiction": cp["jurisdiction"],
            "lei": cp["lei"],
            "governing_law": cp["governing_law"],
            "base_currency": cp["base_ccy"],
            "threshold": cp["threshold"],
            "minimum_transfer_amount": cp["mta"],
            "independent_amount": cp["independent_amount"],
            "cross_default_threshold": cp["cross_default"],
            "automatic_early_termination": cp["aet"],
            "csa_type": cp["csa_type"],
            "products": cp["products"],
            "specified_entity": cp["specified_entity"],
            "additional_termination_events": cp["ate"],
            "effective_date": cp["effective"],
            "agreement_type": "ISDA 2002 Master Agreement",
            "bytes": size,
        })
        print("wrote %-58s %6.1f KB" % (fname, size / 1024))

    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("\nmanifest.json written with %d documents" % len(manifest))


if __name__ == "__main__":
    main()
