# Nalanda Accounts

A private portal where salespeople sign in and see their dealers' outstanding by days, every unpaid bill, and a full PDF statement.
Tally stays the master. A small program on the Tally PC sends the party ledgers up three times a day.

```
Tally PC                                       Netlify (nalandaaccounts)                    Phone or computer
TallyPrime  <-- reads --  Sync agent  --HTTPS-->  Functions API + Blobs storage  <--HTTPS--  Portal (sign in)
 (port 9000)  (never writes)  3 times a day         users, ledgers, bills, statements        PDF in the browser
```

The portal never connects into your PC. Nothing is opened on your network.

## What people can do

| Role | Sees | Can change |
|---|---|---|
| **master** | every dealer and vendor, payables, sync status | users, which dealers belong to which salesperson |
| **accounts** | every dealer and vendor, payables, sync status | nothing |
| **sales** | only the dealers assigned to them, never payables | nothing |

Each dealer page shows: outstanding, the ageing bar (0 to 30, 31 to 60, 61 to 90, over 90 days), every unpaid bill with its days, a statement with a
running balance for a period you choose, and a **PDF statement** button.

## How the numbers are worked out

- Age is counted from the **bill date**, not from a due date. It moves on every day, even between syncs.
- When Tally lists the unpaid bills, those are used. When it does not (ledgers that are not bill wise), the bills are rebuilt from the statement, **newest first**.
  Whatever cannot be matched to a dated bill is shown as "older / opening".
- Every dealer page says whether the bills add up to the ledger balance. Every statement is checked against Tally's own closing balance, and a warning is
  shown on the dealer page if it does not tie.
- A customer who has paid in advance shows Nil outstanding, not a negative number.

## Setting it up

1. **Netlify**: the project is created and deployed for you. Two secrets are stored as Netlify environment variables, never in the code:
   `SESSION_SECRET` (signs sign in cookies) and `SYNC_KEY` (lets the sync agent send data). Change either in Netlify, then redeploy.
2. **First sign in**: the master user starts with a temporary password and must choose their own. Do that first.
3. **Users**: Users tab, Add user. You get a temporary password once. Give it to them, they choose their own at first sign in.
4. **Sync agent**, on the PC that has Tally and Tally Connect installed: `sync_agent\install_agent.ps1`. It asks for the portal address and the sync key, does a
   test read, and schedules three runs a day (default 10:00, 14:30, 20:00, chosen to stay clear of a 6:30 pm Zoho to Tally job).
5. **Assign dealers**: Assign dealers tab. Tick dealers for a salesperson, or paste "dealer name, user name" lines from your dealer mapping sheet.

## Security in plain words

- Passwords are stored as scrypt hashes. Nobody, including the master, can read a password. Resets give a temporary one.
- Five wrong tries lock that user for 15 minutes. Forty wrong tries from one address lock that address.
- A session lasts 7 days and ends at once when the user is disabled, reset or changes password.
- A salesperson asking for a dealer that is not theirs gets the same "not found" as for a dealer that does not exist.
- The page forbids inline scripts and outside resources (content security policy). The PDF library is served from the site itself.
- Sync data is sent over HTTPS with a key. The key lives in the agent's settings file (readable only by that Windows user) and in Netlify.
- Not covered: this is not a bank. Anyone who can use a master or accounts account sees everything. Use strong passwords and disable people who leave.

## Older history for chosen ledgers

By default each statement starts at the beginning of the current financial year. To show more for particular parties, add rules to `agent.json` on the Tally PC:

```json
"history": [
  {"match": "spontan", "from": "2024-04-01"},
  {"match": "narang enterprises", "from": "2024-04-01"}
]
```

`match` is a piece of the ledger name (capitals and extra spaces do not matter). Matching ledgers are sent even when their balance is zero. Keep the rules in `agent.json`: the three daily syncs then keep the long history. A one-off run with `--only` and `--from` does not change what the scheduled syncs send, so the next scheduled run would shrink the statement back.

One-off, without touching the rest of the portal:

```
python -m sync_agent --config agent.json --only spontan --only "narang enterprises" --from 2024-04-01 --include-zero
```

`--only` makes it a partial run: those ledgers are added or refreshed and nothing else is removed. The program prints which Tally ledgers each rule matched, and warns when a rule matches nothing. For a start date other than 1 April of the current financial year, the opening balance is worked out from Tally's closing balance, so the "does it add up" check cannot run for those statements. Compare the first and last balances with Tally once.

## Limits and honest notes

- The Tally report requests for statements and bill wise outstanding follow the standard Tally XML reports. They are tested here against a pretend Tally, **not yet against
  your real Tally**. The first run does a dry run, saves Tally's raw replies, and checks every statement against Tally's balance, so a mismatch shows up immediately.
- Only party ledgers (customers and vendors) are synced, not banks or expenses. Change `kinds` in the agent settings to include others.
- Windows scheduling was written but could not be run in the build environment. If `install_agent.ps1` fails, send the message to Claude.
- Netlify Blobs is a simple store. It suits this size (a few thousand ledgers). If the business grows far beyond that, move to a database.

## Developing

```
npm install
npm test                                  # server tests (no Netlify needed)
NODE_PATH=$(npm root -g) node tests/e2e.mjs /tmp          # browser test, needs playwright
PYTHONPATH=.:<tally-connect>/src python -m unittest discover -s sync_agent/tests   # agent against a fake Tally and the real portal code
SESSION_SECRET=... SYNC_KEY=... node server/local.mjs     # run it locally
```
