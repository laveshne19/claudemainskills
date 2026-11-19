---
name: tally-payments
description: Use for customer receipts and vendor payments, bank entries, and settling invoices. Handles bank statements, payment lists, and posting a receipt or payment against bills.
---

# Receipts and payments

Follow the tally-connect rules. Money entries are where duplicates happen most, so be strict.

## Routine
1. Get the list: an Excel with Date, Party, Amount, Bank, Reference, optionally the invoice numbers. A bank statement
   works too. Read it and put it in that shape.
2. `plan_import(path, "Receipt")` for money in, `"Payment"` for money out. Pass `default_bank` if one bank ledger applies.
3. Show the table. The same party can have two real payments on one day with different amounts, so duplicates are judged on
   date, party and amount together.
4. Held rows usually mean the party or the bank is unclear. Ask the user. Do not pick a bank.
5. After a yes, `post_plan`. Each one is checked by the party balance.

## Rules
- Use the ledger the party already has vouchers in. Never post one payment under two ledgers.
- If two ledgers share a name or GSTIN, use the one that carries the balance, say so, and mention the gap.
- If the receipt settles one invoice, pass it so it is tied to the bill. Otherwise it is booked On Account, and say so.
- Do not touch bank entries the user reconciles by hand.
- Do not test post.
- If the balance in Tally and the other system disagree by a lot, that is a reconciliation job, not a payment job. Report it.
