> Internal document. Remove this file before the repository is made public.

# Product plan: Neural Desk Tally tools

Written for Lavesh, to decide what to build and sell. Prices and the legal points are suggestions, not decisions.

## What exists today

1. **Claude plugin and connector** (this repo). Anyone with Claude and Tally on a Windows PC can install it and post entries
   from Excel or PDF. Built on the workflow already proven daily in the your own books.
2. **Web portal sample** (`website/index.html`). A clickable design of the paid website: landing page, plans, sign in,
   dashboard, upload, review, post. Uses made up data. It exists so the interface can be judged before real build.

## Why people will pay

Tally users in India spend hours typing invoices. Existing tools (Suvit and similar) charge roughly 10,000 rupees a year
for upload and sort portals. The difference here is that the user's own Claude does the reading, the checks are strict
(preview, duplicate refusal, balance proof), and nothing leaves the user's PC.

## Two products

### A. Claude plugin (sold as a download plus license key)
- Customer needs: a Claude subscription, Windows PC with Tally, 10 minutes to install.
- You ship: the installer, the plugin, templates, guides.
- Support: the guides plus the screenshot loop (customers send a screenshot, Claude fixes the setting).
- Pricing idea: one time per company, or yearly for updates. Offer a free demo mode (`tally-connect demo`) so people see it
  work without Tally.

### B. Web portal (subscription)
The browser cannot talk to a Tally on someone's PC, so the portal needs a small **Windows helper** that sits next to Tally,
reads the local gateway, and keeps an outbound encrypted connection to your server. Same pattern as the earlier plan for the
consolidation dashboard (office agent pushes to the server, the server never reaches in).

```
Browser (portal)  <->  Neural Desk server  <->  outbound connection  <->  Windows helper  <->  TallyPrime
                          accounts, billing, AI sorting, review queue            runs tally_connect engine
```

Build order:
1. The helper reuses this engine unchanged (it is already a library).
2. Server: accounts, plans, file upload, AI document reading, review queue, an audit log.
3. Portal: the screens in `website/index.html`.
4. Billing: Razorpay for rupees with GST invoices. Monthly, yearly, lifetime plans.
5. Hard rule: every posting still goes through preview, confirm and the balance proof. Only the user's approval clicks
   change from chat to buttons.

Data handling: invoices are sensitive. Encrypt in transit and at rest, delete uploads after processing, keep an audit trail,
write a privacy policy and terms before charging. Do not store Tally credentials. There are none.

## Plans (suggested starting point)

| Plan | Idea | Starting price |
|---|---|---|
| Monthly | 1 company, up to 500 entries a month | 999 rupees |
| Yearly | 1 company, up to 6000 entries, priority fixes | 7,999 rupees |
| Lifetime | 1 company, this major version, fair use limit | 24,999 rupees |
| Practice | 10 companies, for accountants | on request |

Test pricing with the first ten customers before fixing it. Lifetime needs a clear limit written in the terms, otherwise
support cost grows forever.

## Proven in daily use but not yet in the connector

- Outstanding and ageing sheets by salesperson (bill date based, FIFO, ties to Tally ledger totals, A4 print).
- Daily salesperson emails and WhatsApp follow-ups.
- Bank statement reconciliation between Zoho and Tally.
These are natural paid add-ons once the posting core is proven on real books.

## Busy

Busy does not expose the same HTTP/XML gateway Tally does. The practical route is to generate the Excel or XML import files
that Busy already accepts, and let the user import them in Busy. That needs a sample import file for each document type from a
real Busy installation. Plan: an `AccountingBackend` interface in the engine, Tally first, Busy export second. Not built yet.
Ask for Busy sample files and screenshots and it can be done.

## Zoho and other software

The zoho-to-tally skill already covers Zoho Books (with the Zoho Books connector in Claude). Other systems follow the same
shape: pull documents, normalise, plan, review, post.

## Legal and licensing

- The earlier community connector "TallyMind" (by CA Shailesh S Wadhawaniya, MIT license) was used in the the pilot company work and was
  patched locally. It is third party. This repo is written from scratch and copies none of it. Do not ship the patched copy.
  If you ever merge any of its code, keep its MIT notice.
- Replace `LICENSE.md` with real terms. Add a clear disclaimer: the software posts what the user approves, users must review
  entries, and a chartered accountant's review is their responsibility.
- "Tally" and "TallyPrime" belong to Tally Solutions. Use them descriptively ("works with TallyPrime"), do not suggest
  endorsement, and check their brand guidelines before using logos.
- Privacy policy and terms before taking money. GST invoice for every payment.

## Next steps

1. Run `docs/LIVE-TEST-CHECKLIST.md` on a real company. Fix what differs.
2. Install on two friendly accountants' PCs. Watch where they get stuck.
3. Pick the name and the domain, then point the website at the real server.
4. Build the Windows helper and the server.
5. Collect Busy sample files.
