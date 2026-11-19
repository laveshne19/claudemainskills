# How it works

```
You + Claude  <->  tally-connect (MCP server, on your PC)  <->  http://localhost:9000  <->  TallyPrime
                          |
                          +-- Excel / CSV reader, matching, GST logic, duplicate checks, state log
```

No cloud relay. The Excel is read on your PC. If you attach a PDF in chat, Claude reads it as part of the conversation.

## Reading from Tally

TallyPrime exposes an XML interface on port 9000. We ask it for ledgers, stock items, balances and the Day Book, always one
company, one ledger or one day at a time, with retries, because Tally drops connections under load. Control characters Tally
sometimes emits are cleaned before parsing.

## Writing to Tally

Two shapes of voucher, both proven on a real installation:

- **Invoice view** (Sales, Purchase, Credit Note, Debit Note): stock lines with a godown and batch allocation, the sales or
  purchase ledger on each line, the full GST identity fields, ship to and bill to, `LEDGERENTRIES.LIST` for the party and
  tax, and a **bill allocation with the real invoice number** so Tally files it as a proper bill and ageing stays right.
- **Accounting view** (Receipt, Payment, Contra, Journal): `ALLLEDGERENTRIES.LIST`, no stock, bill references when it
  settles an invoice, otherwise On Account.

Sign convention is Tally's: debit negative, credit positive. Callers give positive numbers and the signs are applied by
document type, so nobody has to remember them.

| Document | Items and tax | Party |
|---|---|---|
| Sales | credit | debit |
| Purchase | debit | credit |
| Credit Note | debit | credit |
| Debit Note | credit | debit |

## The safety chain

1. **Validate:** items plus tax plus round off must equal the invoice total, to the paisa. A rupee difference is allowed as
   round off. More than that is an error.
2. **Match:** party by GSTIN, saved mappings, exact, substring, token overlap. Ambiguity is held, never guessed.
3. **Duplicate check:** our own log, then a live Day Book lookup for that voucher number on that date.
4. **Preview:** XML is built and stored under a single use id, nothing is sent.
5. **Confirm:** one send, never retried. If the reply is lost, the party balance decides what happened.
6. **Verify:** the party balance must move by exactly the invoice amount. The Day Book is not used for proof because it can
   lag. If it does not match, stop everything.

## Things the connector deliberately avoids

Raw SQL on the Voucher collection and Object exports (both hang or crash Tally), bulk edits of ledger masters (opening
balances got corrupted once), deleting vouchers through the API (it fails and leaves screens open), and sending an opening
balance when creating a ledger.

## Settings

`%USERPROFILE%\.tally-connect\config.json`. Company GSTIN and state, ledger name patterns, default godown and batch, freeze
date, read only. Claude changes them through `update_settings` after you agree.

## Files it keeps

`config.json`, `state.json` (previews and the posted log), `party_name_map.json`, `item_name_map.json` (names you approved).
All plain JSON, all on your PC.
