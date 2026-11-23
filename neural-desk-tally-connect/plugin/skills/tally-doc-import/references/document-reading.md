# Reading source documents

## PDFs
- Try text extraction first. Only render pages to images when the PDF is scanned.
- Multi invoice PDFs: split by the invoice number header. Check that the numbers are consecutive.
- Re add the lines and compare with the printed total. Differences of a rupee or two are round off. More than that means
  you misread a column, so look again.
- A line amount can be tax inclusive or tax exclusive depending on the template. Check: does amount times rate percent
  equal the stated tax? If yes the amount is already the taxable value. Never assume, and never build ninety vouchers off an
  unchecked assumption.
- Use "Total Amount After Tax". Ignore "Balance Due" completely.
- Place of supply is the ship to state, which can differ from the bill to state.
- Skip drafts and placeholders the user has told you about.

## Images and photos
Read them directly. If a digit is unclear, say which one and ask. Never fill a number you cannot read.

## Amazon style channel sheets
One row per line, many rows per invoice, one consolidated party ledger for the channel, a sale ledger already named per row
(for example an IGST ledger for out of state and a local ledger for home state). Keep that ledger as given.
Excel dates can arrive as serial numbers such as 46265, which is 31 Aug 2026. The tool converts them.
