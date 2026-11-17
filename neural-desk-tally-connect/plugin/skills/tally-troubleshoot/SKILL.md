---
name: tally-troubleshoot
description: Use when Tally Connect fails, Tally does not answer, an entry is rejected with no error text, a voucher looks wrong in Tally, totals do not match, or Claude cannot see the tally tools.
---

# Troubleshooting

Find the symptom, apply the fix, and ask for a screenshot when the cause is on the user's screen.

| Symptom | Cause | Fix |
|---|---|---|
| Tally does not answer | Tally closed, no company, a dialog open, wrong port | Open Tally and a company, press Esc to the Gateway, check F1 Settings Connectivity, port 9000 |
| Works on the Tally PC, not from another PC | Firewall rule only on Public | Allow tally.exe for Domain, Private and Public |
| Connection reset or dropped on big requests | Tally overloaded or two clients at once | Close the other Claude window. Requests are done one day or one ledger at a time with retries |
| Import says created 0, exceptions 1, no detail | A name does not exist exactly, a missing godown on a stock line, missing GST fields, or a dialog is open | Check ledger and item names letter by letter, run discover_setup, check the default godown, press Esc in Tally |
| Entry posted but looks like an "Accounting Voucher" | Invoice view flags missing | Reinstall the latest connector, it sets the invoice view |
| Shows as On Account dated today | Bill reference missing | The current version always sends the invoice number as the bill reference |
| Tax shows against the party, not the tax ledgers | Tax ledger names differ in this company | Run discover_setup and fix names with update_settings. Ask for a screenshot of the voucher |
| Items or totals look doubled | Duplicate voucher number, or an old alteration screen left open | Do not repost. Ask the user to find and delete the duplicate in Day Book. Never reverse |
| Footer total on the voucher screen looks wrong | The footer just adds the visible amount column | Ignore it. Check the party balance change instead |
| The Day Book does not show the new entry | The Day Book can lag | Trust the balance check. Do not repost |
| Balance check failed | Another user posted at the same time, or the entry went elsewhere | Stop. Ask the user to look at the voucher. Do not post more |
| Timeout while posting | Tally was slow | The tool checks the balance. Never post again without checking |
| Claude cannot see the tally tools | A resumed chat does not load tools, or the server crashed on start | Start a brand new chat. Run tally-connect doctor in a terminal. Reinstall if it fails |
| Server crashes on start with an mcp or FastMCP error | An old connector on a new MCP SDK | This connector supports both. Update it |
| Party or item not found | Spelling, "&" versus "and", a branch suffix, different GSTIN | Use the GSTIN, then the address. Ask the user before creating anything |
| Dates look wrong | Day and month swapped | Dates are read as day first. Check the warnings |
| Educational edition | Date ranges silently truncated | Use Silver or Gold |

## Never do these
- Do not run raw SQL against the Voucher collection. It throws a dialog that blocks Tally and has crashed it.
- Do not use Object type exports. They hang Tally.
- Do not alter or delete existing vouchers or bulk change ledger masters through the API. Opening balances were corrupted
  this way once. Ask the user to change them in Tally.
- Do not post test entries in live books.

## When you are stuck
Ask for: a screenshot of the Tally screen, the exact message, the voucher number, and what was just posted. Then compare
the screenshot with the entry you built, find the single difference, and fix only that.
