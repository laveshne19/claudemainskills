# Market research: how similar tools work

> Internal document. Remove before the repository is made public.
> Source quality: web search summaries only. The vendor pages, Tally's help pages and the video summaries could not be opened
> from the build environment (network blocked), so nothing below was read on the vendor's own page. Treat feature and price
> claims as marketing until checked.

## Suvit (the main comparison)

- Reads Excel, PDF and scanned images with AI and OCR, and pushes entries into Tally. [Suvit feature page](https://suvit.io/data-entry-automation-feature)
- Flow: choose the module (vouchers, ledgers, stock items), upload, map columns to Suvit fields, verify, push to Tally in a few clicks.
- A desktop connector sits next to Tally. New ledgers or items created in Tally must be pulled in first with a "Sync Master" step.
- Claims validation checks, for example flagging a missing GST number.
- Price: listings say about 10,000 rupees to start (Capterra, Techjockey), CA plans 10,000 to 20,000. One listing says 120 dollars a month. Not
  confirmed on Suvit's own site. [Capterra](https://www.capterra.co.nz/software/1078111/Suvit), [Techjockey](https://www.techjockey.com/detail/suvit)

What this means for us: the shape is the same (upload, map, verify, push, with a connector). We differ by running the reading
in the customer's own Claude, the hard safety chain (duplicate refusal, balance proof, held questions), and no data leaving the PC.

## Tally's own Excel import

- Tally ships a Mapping Template that links Excel columns to voucher fields. Header row is set (usually row 1), data from row 2.
- Official samples: sales vouchers with multiple rows per invoice, and multiple columns with bill allocations. [Tally help](https://help.tallysolutions.com/tally-prime/import-data/download-sample-excel-files-with-data-for-import)
- Rule from guides: all ledgers used in the sheet must already exist in Tally, or the import fails.
- Multi-row layout: same voucher number repeated on each item row.
- Video walkthroughs exist (Hindi, "Import Data From Excel to Tally Prime"). Summaries: [Recapio](https://recapio.com/digest/import-data-from-excel-to-tally-prime-puure-saal-kii-entries-ek-hii-baar-men-import-kren-file-itr-by)

Idea: add an export mode that writes a sheet in Tally's own sample layout, as a fallback for people who do not want a live connection.

## Busy

- Path: Administration, Data Export/Import, Import Vouchers from Excel. Choose the voucher type, set a saved Format that maps each Busy field to an
  Excel column, name the sheet, run. [Busy FAQ](https://busy.in/faqs/what-is-the-process-for-importing-data-from-excel-to-busy-answerid-55977/)
- One row per line item, invoice level fields repeated, so rows group by invoice number. [Guide](https://invoicedataextraction.com/blog/import-purchase-invoices-into-busy-from-excel)
- Common failures: columns not assigned in the format, antivirus blocking on cloud or remote setups. Test a small sample first.

Plan for Busy: generate the Excel plus a one page "how to set up the format" with screenshots, per voucher type. Needs sample sheets and format
screenshots from a real Busy install to get exact.

## Domains (GoDaddy check, not purchased)

| Domain | Status |
|---|---|
| neuraldesk.com | available |
| neuraldesk.ai, .in, .io, .app, .co.in | taken |
| neuraldesk.co, .pro, .tech, .software, neural-desk.com | available |
| tallyconnect.ai, tallyconnect.in, tallyconnect.io | available |
| neuraltally.com, neuraltally.ai | available |
| indiainvoice.ai, smartledgerai.ai | available |
| tallybot.com, deskbrain.com | available, premium price |
