# Prompt for the Tally chat

Copy everything inside the box below and paste it into Claude Code on the Tally PC (the chat where TallyPrime runs).

````text
I want you to set up and run the Nalanda Accounts portal sync on this PC, using work that is already built and tested in my GitHub repo. Do it step by step, test each step, and tell me plainly what worked and what did not. Do not guess: if something fails, show me the real error.

ABOUT THE REPO
- Repo: laveshne19/claudemainskills, branch claude/clever-volta-w5e2at
- Folder neural-desk-tally-connect = Tally Connect (Python package tally_connect, talks to TallyPrime on localhost:9000)
- Folder nalandaaccounts = the private portal (live at https://nalandaaccounts.netlify.app) plus sync_agent/, the program that reads Tally and sends ledgers to the portal
- Read nalandaaccounts/README.md first, especially "Older history for chosen ledgers".

RULES
- The sync only READS from Tally. Never write, create, alter or delete anything in Tally.
- Never print, log, commit or paste the portal sync key anywhere. Ask me for it when needed and store it only in the NALANDA_SYNC_KEY environment variable or in agent.json outside the repo.
- Do not touch the portal's users or passwords.
- Do not use em dashes in anything you write for me. Keep messages plain and short, like a person wrote them.

STEPS
1. Check this PC: Windows version, Python 3.10 or newer (install it if missing, tell me first), git. Confirm TallyPrime is open with my company loaded and the gateway is on (F1 Help > Settings > Connectivity > Client/Server, set TallyPrime as Server, port 9000). Test with a simple request to http://localhost:9000 and tell me the company names it returns.
2. Clone the repo on the branch above into a normal folder (for example C:\NeuralDesk). Install tally_connect from neural-desk-tally-connect (pip install in a venv).
3. Run the tests so we know the build is good:
   - in nalandaaccounts: node --test tests/core.test.mjs (if Node is installed, otherwise skip and say so)
   - in nalandaaccounts: python -m unittest discover -s sync_agent/tests (set PYTHONPATH to the repo's nalandaaccounts folder and neural-desk-tally-connect/src)
   Report the pass counts.
4. Create agent.json in %USERPROFILE%\.nalandaaccounts\ from sync_agent/agent.example.json. portal_url is https://nalandaaccounts.netlify.app. Ask me for the sync key. If more than one company is open in Tally, ask me which one and set "company". Keep the "history" rules for these two parties from 1 April 2024:
   - match "spontan" (I may have spelled it wrong, the real ledger could be "Spontaneous ...")
   - match "narang enterprises"
5. First a dry run, nothing sent:
   python -m sync_agent --config <path>\agent.json --only spontan --only "narang enterprises" --from 2024-04-01 --include-zero --dry-run --debug-dump <folder>
   Show me which Tally ledger names each rule matched. If a rule matches nothing, list the nearest ledger names from Tally and ask me which one is right. If the report XML does not parse (zero vouchers for a ledger that clearly has entries), look at the dump files, fix the parser in sync_agent/agent.py, add a test for the real shape, and rerun the tests.
6. When the dry run looks right, run it for real (same command without --dry-run). This is a partial run, so it keeps everything else on the portal. Then open the portal API or the site and confirm both ledgers show with statements from April 2024, and the first and last balances match Tally. Tell me both numbers side by side. For a start date outside the current financial year the tie-out check cannot run, so this manual comparison matters.
7. Then ask me before doing the full sync. A full run replaces the sample data on the portal with my real Sundry Debtors and Sundry Creditors. When I say yes, run it, and report ledgers sent, warnings, and any statements that did not tie out.
8. Set up the schedule: run nalandaaccounts/sync_agent/install_agent.ps1 (or create the Windows Task Scheduler jobs by hand) so the sync runs 3 times a day at 10:00, 14:30 and 20:00. My 6:30 pm Zoho job must not clash. Run the task once manually and show me the log.
9. Finish with a short summary: what is installed and where, what is scheduled, what I should check in Tally, and anything still open. If you changed any code, commit it on a new branch and tell me, do not push to main.

If a step needs something only I can do (the sync key, choosing a company, switching Tally to Server mode), stop and ask me clearly.
````

## If the repo is private on that PC

Run `gh auth login` first, or give Claude Code a GitHub token that can read `laveshne19/claudemainskills`. Do not paste the token into this prompt.
