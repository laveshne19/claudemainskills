# Collections and outstanding portal (a CredFlow style tool)

> Internal planning document. Remove before the repository is made public.
> Status: planning only. Build starts after the Tally Connect desktop test is done.
> Research limits: product pages could not be opened from the build environment. The notes below come from search result
> summaries and listings, so treat feature and price claims as unverified until checked on the vendor's own site.

## What you described

- Fetches data from Tally and shows receivables and payables in a very simple way.
- Sends payment reminders by WhatsApp, through the official WhatsApp API.
- Shows every invoice and every ledger.
- Has an app on Play Store and App Store.
- The Tally data refreshes every 20 to 30 minutes.
- One company is connected at a time. A master user creates more users below it, so every salesperson can log in.
- Salespeople get limited access, like the salesperson sheets already used for Nalanda.
- The main value: Tally does not easily show ledgers sorted by days overdue, which invoice is outstanding, and how late each one is.
  This tool shows that with accurate data.

## What the market tool does (CredFlow, from listings)

- A Tally and Busy mobile app for collections and cash flow. App Store and Play Store listings exist. [App Store](https://apps.apple.com/in/app/credflow/id1495837286)
- Reminders to debtors by SMS, WhatsApp, email and call, from an Overdue screen. Manage several companies and users from one account. [App Store listing](https://apps.apple.com/in/app/credflow/id1495837286)
- Ageing analysis of debtors, cash flow projection, receivables in one place. Another listing says the Lite plan has email reminders only, so WhatsApp may
  depend on the plan. [Techjockey](https://www.techjockey.com/detail/credflow)
- Pricing is inconsistent across listings: about 3,499 (Lite) and 6,999 (Saver) a year on one aggregator, and 999 plus GST on another.
  [SoftwareOne](https://platform.softwareone.com/product/credflow-tally-on-mobile/PCP-2740-6997)
- One App Store reviewer reported that sync from Tally was not working. Sync reliability is the thing to beat.
- Competitors: Takkada (field invoicing, WhatsApp, UPI collection), Biz Analyst, AI Accountant. Their comparison pages are written by themselves.
  [Comparison page](https://landing-3si.pages.dev/blog/best-credflow-alternatives-india-2026)
- TallyPrime itself has outstanding and ageing reports and can send reminders, with default slabs 0 to 45, 45 to 90, 90 to 180 and over 180 days.
  [Tally guide](https://tallysolutions.com/business-guides/how-to-track-receivables-aging-and-send-payment-reminders-in-tallyprime/)

## What we already know from the Nalanda work (this is the real edge)

- Ageing is by **bill date**, never Tally's own overdue field. Newest bills are matched first (FIFO) against the ledger balance, and the total must tie to
  the Tally ledger balance to the rupee.
- Some ledgers are bill wise and some are not. A non bill wise ledger would otherwise show its whole balance as one bill dated today, which gives a false age
  of zero days. Those need their own method (rebuild from sales and credit note history) and an honest "older or opening" bucket.
- Cash dues sit on top. Shared dealers appear under every salesperson mapped to them. The dealer mapping sheet is the authority for who sees what.
- Tally drops connections under load, so the sync must ask one day or one ledger at a time, retry, and never hit Tally from two programs at once.
- The Day Book can lag and raw voucher SQL can crash Tally. The proven reads are ledger and stock lists, outstanding exports and per day Day Book.
- Tally is on a private office address, so the cloud can never reach in. An office agent must push out.

## Proposed design

```
Office PC (Tally, port 9000)
  Sync agent (the same gateway code as Tally Connect), every 20 to 30 minutes, outbound HTTPS only
        |
        v
Cloud service
  API + database (companies, ledgers, bills, vouchers, users, roles)
  Ageing engine (bill date, FIFO, bill wise and non bill wise, tie out to Tally)
  WhatsApp sender (official Cloud API, approved templates, opt in, send log)
        |
        v
Web portal and phone app (same screens, installable web app first, store apps later)
```

### Users and access
- Master user per company, creates sub users (salesperson, accountant, viewer).
- Salesperson sees only the dealers mapped to them, with outstanding, bill list, ageing and a "send reminder" button for their dealers.
- Optional: hide payables and totals from salespeople. Every action goes in an audit log.
- One company connected per account at first, as you said. More companies later for accountants.

### Screens
1. Home: total receivable, total payable, overdue buckets, top overdue dealers, cash due.
2. Receivables: dealer list sorted by days overdue, filters by salesperson, city, state, bucket. Click for the bill list with invoice number, date, amount, days.
3. Payables: the same for vendors.
4. Ledger and invoice view: statement, all invoices, payments received.
5. Reminders: pick dealers, preview the WhatsApp message, send, see delivery status and replies.
6. Users: master creates and edits sub users and their dealer lists.
7. Sync status: last sync time, errors, a "sync now" button.

### WhatsApp
- Use the official WhatsApp Business Cloud API (or a provider built on it, such as the Zoho or another approved partner). Reminders go out as pre approved
  message templates. Customers must have opted in. Costs are per conversation. Keep a send log and a stop list.
- Never auto send without the master's rules (for example, only bills older than 15 days, once a week per dealer).

### Phone app
- Phase 1: installable web app (PWA). Works on Android and iPhone, no store review, one codebase.
- Phase 2: Play Store and App Store wrappers once the screens are proven. The store listings need a privacy policy, account deletion and review time.

### Security and trust
- Outbound only from the office PC. No ports opened on the customer's network.
- Encrypt in transit and at rest. Per company data separation. Role checks on every request. Audit log. A privacy policy before taking customers.
- Customer data is sensitive: only store what the screens need.

## Build order

1. Finish and live test Tally Connect (in progress).
2. Sync agent: reuse the gateway, add ledger outstanding and bill list reads, ageing engine with the Nalanda rules, tie out checks. Test on the Nalanda data.
3. Cloud API and database, users and roles, the salesperson mapping.
4. Web portal and PWA with the screens above, using the same design as the Neural Desk portal.
5. WhatsApp reminders with templates and rules.
6. Store apps, billing, and a trial for 5 to 10 distributors.
7. Add it to the Neural Desk portal as a second tool.

## Questions to settle before building

- Who is it for first: your own company, or other distributors from day one?
- WhatsApp: which provider or number do you already have approved? A template approval takes time, so start it early.
- Price idea: per company per year with a set number of users, or per user?
- Do salespeople need to see payables, or only receivables?
- Is Busy needed at launch? Busy has no live gateway like Tally, so it would need a different sync route.
