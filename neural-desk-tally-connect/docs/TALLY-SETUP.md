# Setting up Tally and your company

Do this once per company. Claude can walk you through it: type `/tally-setup`.

## 1. Tally connection (about two minutes)

1. Open TallyPrime and load the company you will post into. Use Silver or Gold. The Educational edition quietly cuts off
   date ranges, which breaks duplicate checks.
2. Press **F1 (Help)**, then **Settings**, then **Connectivity**, then **Client/Server configuration**.
3. Set **TallyPrime acts as** to **Server** or **Both**. Port **9000**. Turn **ODBC server** on if it is shown.
4. Go back to the Gateway of Tally. Press Esc until no box is open. An open dialog stops Tally from answering.

Take a screenshot of that settings screen and send it to Claude if you are not sure.

## 2. Tell Claude about your company

Claude asks for your company GSTIN and state. The state decides IGST or CGST plus SGST. Chandigarh and the other union
territories without a legislature use CGST plus UTGST.

## 3. Ledger names

Every company names its GST and sales ledgers differently. Claude scans your ledgers and proposes the names, for example
`CGST OUTPUT`, `UTGST OUTPUT`, `IGST OUTPUT`, `ROUND OFF`, `SALES LOCAL@ 18%`. You confirm or correct them once.

## 4. Stock settings

If you track godowns, tell Claude the default one (often `Main Location`). Stock entries fail silently in Tally without a
godown, so this matters.

## 5. Safety settings

- **Freeze date:** nothing dated before it is ever touched.
- **Read only:** nothing can be written. A good way to start.

## 6. The first real entry

Pick one real document. Claude shows the preview, you say yes, and then you open that voucher in Tally and send Claude a
screenshot. If anything looks different from your own manual entries, Claude adjusts the settings. After that, post in bulk.

## Good habits

- One Claude window at a time per Tally.
- Keep Tally open on the Gateway of Tally while posting.
- Back up your Tally data the way you already do. Tally Connect does not copy or move your data files.
- Do not test in live books.
