# Neural Desk Tally Connect

Upload your sales invoices, purchase bills, credit notes, debit notes, receipts and payments as Excel or PDF, and
Claude posts them into TallyPrime. You see a review table first, you answer anything that is unclear, you say go, and
every entry is checked against the party balance in Tally afterwards.

It runs on your own PC, next to your own Tally. Your books never leave your machine.

## What you get

| Piece | What it is |
|---|---|
| `src/tally_connect` | The connector. A Python package, the desktop app (`tally-connect app`), an MCP server for Claude, and a command line tool. |
| `desktop/` | Windows launchers and the read-me-first for the desktop test build. `scripts/build_release.py` makes the zip. |
| `plugin/` | The Claude plugin: skills that teach Claude the routine and the safety rules, plus slash commands. |
| `installer/install.ps1` | One script that installs everything on Windows and links it to Claude Desktop and Claude Code. |
| `templates/` | Excel templates for each document type. |
| `website/index.html` | A clickable sample of the web portal, for reviewing the interface. |
| `docs/` | Install guide, user guide, Tally setup, how it works, product plan, live test checklist. |

## Desktop app

Run it on the PC that has Tally. It opens in your browser, on your own machine only.

```
tally-connect app            # real Tally
tally-connect app --demo     # simulated Tally, nothing to install in Tally
```

Tabs: Import (upload, review, answer held questions, post), Setup (connection, company, ledger names, safety settings), History,
Help (copies a diagnostics report to send to Claude together with a screenshot). Excel and CSV are read here. PDFs and photos are
read by Claude with the plugin.

## Ten second tour (no Tally needed)

```
pip install .
tally-connect demo
```

This starts a simulated Tally, reads a sample sheet, posts it, and prints the balance check. The simulator is for trying
and testing only. It is not TallyPrime.

## Real use

1. Install: see `docs/INSTALL.md`.
2. Set up your company: see `docs/TALLY-SETUP.md`.
3. In Claude, start a new chat and say: `check the Tally connection`. Then: `import this file` and attach your Excel.

## The safety model in one paragraph

Nothing is written without a preview and your yes. Ledgers and stock items are never created without your approval.
Duplicates are refused before posting, by our own log and by a live Day Book check. Writes are never retried blindly.
After every entry the party balance must move by exactly the invoice amount, otherwise everything stops. Old periods can
be frozen, and a read only mode is available for the first day.

## Status, honestly

- Built from a protocol that was worked out against a real TallyPrime installation over several months of daily use.
- 73 automated tests, an MCP end to end test on both major MCP SDK versions, and a 29 step browser test of the desktop app all
  pass, against a simulated Tally. The same browser test passes against the installed release zip in a clean environment.
- **Not yet run against a live TallyPrime from this build.** Do the checklist in `docs/LIVE-TEST-CHECKLIST.md` on the first
  day. Expect to adjust ledger names and the godown for each company. That is what the setup step is for.
- Windows installer written and reviewed, not yet run on Windows.
- Busy support is a plan, not a feature. See `docs/PRODUCT-PLAN.md`.

## Tests

```
python -m unittest discover -s tests
python tests/mcp_smoke.py
NODE_PATH=$(npm root -g) node tests/e2e_ui.js /tmp        # needs node and playwright
python scripts/build_release.py                             # builds dist/TallyConnect-Desktop-<version>.zip
```
