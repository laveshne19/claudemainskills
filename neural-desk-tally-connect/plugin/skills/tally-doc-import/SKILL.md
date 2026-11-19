---
name: tally-doc-import
description: Use when the user uploads or points to an Excel, CSV, PDF or images of sales invoices, purchase bills, credit notes, debit notes, receipts or payments and wants them entered in Tally. Reads, sorts, matches, shows a review table and posts after approval.
---

# Document import

Follow the tally-connect skill rules throughout. This skill is the routine for a batch.

## 1. Get ready
Run `tally_doctor`. Confirm the company. Check the company GSTIN and state are set (`get_rules` shows them), because
they decide the GST split.

## 2. Read the documents
- **Excel or CSV:** call `plan_import(path, voucher_type)`. It finds the header row, understands common column names,
  groups rows by invoice number, checks that items plus tax equal the total, matches parties and items, and sorts every
  document into READY, HELD, DUPLICATE or ERROR. It writes nothing.
- **PDF or images:** read them yourself. For text PDFs extract the text first, it is faster and more accurate than
  looking at images. Pull out date, number, party, GSTIN, ship to state, each line (item, HSN, qty, rate, amount),
  tax, and the total after tax. Put the result into an Excel using the template (`tally-connect templates`) or call
  `preview_invoice` per document. See references/document-reading.md.
- If a sheet has columns you do not recognise, ask the user what they mean. Do not guess a column.
- Dates: Indian order, day first. The tool warns when a date could be read two ways. Show those warnings.

## 3. Show the review table
Show one table with number, date, party (and the Tally ledger it matched), total, GST lines and status. Then:
- Say how many are READY, HELD, DUPLICATE and ERROR, and the total of the READY ones.
- Report any gaps in the invoice number series. The series must stay complete. Do not enter placeholders or drafts the user
  told you to skip.
- Note every match that was not exact, for example "Rocker Summit Classic Black matched to Rocker Summit Black".
  Colour or a trailing variant word is fine. Two different products are not.

## 4. Put the held questions to the user
Each HELD row carries the exact question. Ask them together, short, with options:
- Party not in Tally: "Create X as a new customer ledger, or is it an existing party under another name?"
- Item not in Tally: "Map X to the closest existing item (suggest it), or create it as a new item?"
- Ambiguous: list the candidates and ask which.
When the user answers with a mapping, save it with `remember_mapping` so it is automatic next time. If they approve a
new ledger, use `preview_ledger` then `confirm_import`, then plan again.

## 5. Post
Only after the user says go, call `post_plan(plan_id)`. It posts one at a time, each with preview, confirm and a
balance check, and stops at the first problem. Report per document: posted and verified, or what went wrong.
For a handful of documents you can also use `preview_invoice` and `confirm_import` yourself.

## 6. Close out
Give a short summary: posted, held, skipped as duplicates, errors, total posted against the total in the file. Say
clearly that the Day Book can lag, and that the balance check is the proof. Offer to run the held ones once answered.

## Document types
| Document | voucher_type | Party side | Notes |
|---|---|---|---|
| Sales invoice | Sales | debit | tax goes to Output ledgers |
| Purchase bill | Purchase | credit | tax goes to Input ledgers |
| Credit note (sales return) | Credit Note | credit | add the original invoice number if known |
| Debit note (purchase return) | Debit Note | debit | same |
| Customer receipt | Receipt | credit | use `plan_import` with type Receipt |
| Vendor payment | Payment | debit | same |
For anything else (Contra, Journal, stock journals) say it is not automated yet and ask for a sample.
