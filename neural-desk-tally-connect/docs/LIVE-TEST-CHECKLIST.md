# First day on a real TallyPrime

This build was tested against a simulator. Real Tally has quirks, so do these in order on a **copy of the company** if you
can, or on a day when a mistake is easy to delete. Send Claude a screenshot at every step marked (screenshot).

- [ ] Tally on Silver or Gold, company open, Server mode, port 9000. (screenshot of the settings)
- [ ] `tally-connect doctor` says reachable and lists the company.
- [ ] `discover_setup` finds your GST ledgers, sales ledgers, banks. Fix any wrong names. (screenshot of the ledger list if unsure)
- [ ] Set company GSTIN, state, default godown, freeze date. Start in read only.
- [ ] Read only run: plan a real sheet. Check the READY, HELD, DUPLICATE split against what you know.
- [ ] Turn read only off. Post ONE sales invoice. Open it in Tally. (screenshot)
  - [ ] Opens in the Invoice view, not the plain voucher view.
  - [ ] Party details show GSTIN, state, place of supply.
  - [ ] Tax sits on the tax ledgers, not on the party.
  - [ ] Bill reference is the invoice number, dated the invoice date, not "On Account" today.
  - [ ] Godown and batch are right. Item rate and quantity are right.
  - [ ] Total equals the source. Round off is correct.
  - [ ] The balance check passed.
- [ ] Try a second invoice for an out of state party (IGST).
- [ ] Try a credit note against an invoice.
- [ ] Try a purchase bill.
- [ ] Try a receipt tied to one invoice, then check the outstanding report in Tally.
- [ ] Post the same invoice again. It must refuse as a duplicate.
- [ ] Post a small batch (5 to 10). Compare the totals with the file.
- [ ] Close the Tally company and run doctor. It must explain what to do.

## If something differs

Send Claude the screenshot and what you expected. Typical fixes: ledger name patterns, default godown, class name, whether
the company needs batch details. If Tally rejects an entry with no message, the cause is almost always a name that does not
match letter for letter, a missing godown, or a dialog box open in Tally.

## Known unknowns from this build

- **Bill reference.** The connector sends a bill allocation carrying the invoice number so Tally files the invoice as a proper
  bill. The scripts it was modelled on did not send one, and the owner saw "On Account" dated the posting day with another
  connector. If the first test shows anything odd in the bill, outstanding or ageing, set `send_bill_allocations` to false in
  the settings and test again. Tell us which way your Tally behaves.

- The exact XML field names used to read party GSTIN and state from ledgers (`PartyGSTIN`, `LedStateName`) were taken from
  working scripts but should be confirmed on first run. If `find_ledger` by GSTIN never hits, send a screenshot of a ledger
  screen and the output of `tally-connect doctor`.
- Day Book field names for voucher number and party come from the working protocol. If duplicate detection by Day Book finds
  nothing on real data, our own log still protects against repeats, and the balance check still proves each posting.
- Bill allocation and invoice view on your Tally release: confirmed on TallyPrime 3.x in daily use. Older releases not tested.
