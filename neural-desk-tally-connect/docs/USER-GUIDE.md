# User guide

## The daily routine

1. Open Tally and your company. Open Claude, start a new chat.
2. Say: `check the Tally connection`.
3. Attach your file and say what it is: `import these sales invoices`, `these are purchase bills`, `these are customer
   receipts`.
4. Claude shows a table. Each line is one of:
   - **READY**: matched and balanced, can be posted.
   - **HELD**: needs a decision, with the question written out.
   - **DUPLICATE**: already in Tally, skipped.
   - **ERROR**: the numbers do not add up, with the reason.
5. Answer the held questions. Typical ones: a new customer with no ledger, an item that is not in Tally, two similar names.
6. Say `go`. Claude posts one at a time and checks each one. You get a summary.

## Document types

| You have | Say | Excel template |
|---|---|---|
| Sales invoices | sales invoices | `sales_invoices.xlsx` |
| Purchase bills | purchase bills | `purchase_bills.xlsx` |
| Credit notes | credit notes | `credit_notes.xlsx` |
| Debit notes | debit notes | `debit_notes.xlsx` |
| Money received | receipts | `receipts.xlsx` |
| Money paid | payments | `payments.xlsx` |
| PDFs or photos | just attach them | Claude reads them directly |

## The Excel format

One row per item. Rows with the same invoice number become one invoice. Required: invoice number, date, party, item,
quantity, rate. Strongly recommended: GSTIN, ship to state, taxable value, tax, total. The total is the amount after tax.
Never the balance due. Column names are flexible, Claude understands common variations. Dates in day first order or
yyyy-mm-dd both work.

## Things Claude will always do

- Show before posting.
- Match names by GSTIN first, then by name. Colour or variant words at the end of an item name are ignored.
- Report gaps in your invoice number series.
- Prove each entry with the party balance.

## Things Claude will never do

- Create a ledger or item without asking.
- Delete or change an existing voucher.
- Post to a date before your freeze date.
- Post again after a timeout without checking.

## When something looks wrong in Tally

Send a screenshot of the voucher and tell Claude what you expected. It compares it with what it posted, finds the
difference, and fixes the setting. Then it shows you one test entry before continuing.

## Need a different kind of entry?

Tell Claude, send a sample file and a screenshot of how it should look in Tally. New document types are added that way.
