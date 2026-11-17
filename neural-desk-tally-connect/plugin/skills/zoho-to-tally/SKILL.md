---
name: zoho-to-tally
description: Optional. Use when the user keeps invoices, bills and credit notes in Zoho Books and wants them mirrored into Tally, or wants Tally payments mirrored back into Zoho. Needs the Zoho Books connector in Claude as well.
---

# Zoho Books to Tally

Tally stays the master. Zoho is where the document comes from. Needs the Zoho Books connector connected in Claude.

## Daily routine
1. `tally_doctor`.
2. Pull the pending documents from Zoho for the last day or two only: invoices, bills, credit notes, debit notes. Do not
   go back past the freeze date.
3. For each one, check Tally has no entry with that number (the tools do it again before posting).
4. Build the invoice: Total Amount After Tax, ship to state for place of supply, the party's GSTIN, bill to and ship to
   addresses, item lines with HSN. Use `preview_invoice`, or write them to a sheet and use `plan_import`.
5. Show the table. Put every held question to the user. Common ones: a walk in customer with no ledger, items that exist in
   Zoho but not in Tally.
6. After a yes, post. Verify by balance. Report posted, held, skipped.
7. Payments in the other direction: list Tally receipts and payments from the last day or two, check Zoho has none for the
   same party, date and amount, then create them in Zoho. Two contacts with the same name or GSTIN in Zoho: use the one that
   carries the balance and tell the user.

## Rules
- Skip placeholders and drafts the user named. Keep the number series complete otherwise.
- A Zoho item name with a suffix like "(Demo)" or a colour is matched to the closest real Tally item, and the match is shown.
- Never create Tally ledgers or items to match Zoho. Ask first.
- Never edit or delete anything in Tally through the tools.
- Report gaps between the two systems, but do not fix balances by posting fake payments. Use a journal against an opening
  balance adjustment only if the user asks.
