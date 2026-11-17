---
name: tally-first-setup
description: Use the first time a company is connected, or when the connection fails. Walks the user through the Tally settings, finds the company's own ledger names, and does one safe test. Asks for screenshots at each step.
---

# First time setup

Go one step at a time. After each step ask the user to confirm, and ask for a screenshot when a screen is involved.
You cannot see their screen, so a screenshot saves a lot of guessing.

## Step 1. Tally settings (on the Tally PC)
1. Open TallyPrime and load the company. Use Silver or Gold. The Educational edition silently cuts date ranges.
2. Press F1 (Help), then Settings, then Connectivity, then Client/Server configuration.
3. Set "TallyPrime acts as" to Server (or Both). Port 9000. Turn ODBC server on if it is offered.
4. Restart Tally if it asks. Come back to the Gateway of Tally and press Esc until no dialog is open.
Ask for a screenshot of that settings screen.

## Step 2. Test the connection
Run `tally_doctor`. If Tally is on the same PC as Claude, it should say reachable and list the company.
- Not reachable: the firewall is the usual cause when Tally is on another PC. The rule for tally.exe must cover
  Domain, Private and Public. Also check that a dialog is not waiting for a key press.
- Two companies open: set the one to use with `set_company`.

## Step 3. Company details
Ask for the company GSTIN and state. Save them with `set_company(name, gstin, state)`. The state drives the GST split.

## Step 4. Find the company's own ledger names
Run `discover_setup`. Show the user what it found: GST output and input ledgers, round off, sales and purchase ledgers
(for example "SALES LOCAL@ 18%"), banks. Every company names these differently.
- Confirm each one. Fix wrong or missing ones with `update_settings`.
- For sales and purchase ledgers, save the pattern with {rate} where the GST rate appears in the name, for example
  "SALES LOCAL@ {rate}%".
- If the company tracks godowns, ask which is the default and save it. Ask whether stock is tracked by batch.
  If a stock entry later fails with no error text, the godown or the GST fields are the first things to check.

## Step 5. Safety settings
Ask for a freeze date (nothing before it will be touched) and whether to start in read only mode. Starting read only for
the first day is a good habit. Save with `update_settings`.

## Step 6. One real test entry, together
Pick a single real document the user is happy to post. Preview it, show it, post it after a yes, and have the user
open that voucher in Tally and send a screenshot. Compare it with what you posted: invoice view, party details, GST
lines, bill reference. If anything differs, adjust the settings and agree a fix before the batch.
Never post a made up test entry into live books.

## Step 7. Wrap up
Summarise the saved settings. Tell the user the daily routine: upload a file, review the table, answer the held
questions, say go.
