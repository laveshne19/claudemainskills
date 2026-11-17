---
name: tally-connect
description: Use whenever the user wants to read from or enter data into TallyPrime, check a ledger balance, or work with sales, purchase, credit note, debit note, receipt or payment entries. Gives the safety rules and the standard routine. Start every Tally session here.
---

# Tally Connect

You can read from TallyPrime and post entries into it through the tally-connect tools. Tally runs on the user's
own Windows PC, so everything happens on their machine and nothing is sent to a cloud service.

## Start of every session

1. Call `tally_doctor`. If it fails, do not guess. Give the user the steps from the result, one at a time, and ask
   for a screenshot of the Tally screen when they are stuck.
2. Check which company is open. If more than one is open and no company is set, stop and ask which one to use.
3. If this company has never been set up, run the tally-first-setup skill.

## The rules, no exceptions

1. **Tally is the master.** Documents are entered into Tally. The parties and items on a document already exist in
   Tally. Your job is to find them, not to invent them.
2. **Two steps for every write.** Preview first, then wait for the user to say yes, then `confirm_import`. Never
   confirm because the user was vague. "Post", "go", "enter", "yes" are a yes. "Check" and "show" are not.
3. **Never create a ledger or stock item without explicit approval.** Search first: GSTIN, address, spelling,
   "&" versus "and", a trailing branch name. If something plausible exists, show it and ask. A new party is created
   complete (address, state, pincode, GSTIN or a clear Unregistered) or not at all.
4. **No duplicates, ever.** The tools check before every create. If a duplicate shows up anyway, do not fix it with a
   reversal. List it for the user to delete in Tally.
5. **Use Total Amount After Tax.** Never Balance Due.
6. **Place of supply is the ship to state.** It decides IGST or CGST with SGST (UTGST for Chandigarh and the other
   union territories without a legislature).
7. **Prove every posting.** `confirm_import` checks that the party balance moved by exactly the right amount. Report
   that result. If it did not match, stop and say so. Do not post anything else on top.
8. **A timeout is not a failure.** Tally sometimes writes the entry and loses the reply. Never post again after a
   timeout. The tool already checks the balance and tells you what happened.
9. **Do not touch old entries.** Respect the freeze date. Only enter what the user asks for, usually the last day or two.
10. **Never test in live books.** If a test is needed, use `tally-connect demo` or a copy of the company.
11. **Do not run two Claude windows against the same Tally.** It drops connections. If another run is going, wait.

## Talking to the user

Keep it short and plain. Say what you found, what you did, what is held and why. When something needs a decision, ask
the exact question once, with the options. Never pad. Never claim a check you did not run.

## When the screen looks different from what you expected

This is normal and fixable. If a voucher looks wrong in Tally, an error dialog appears, or a ledger name differs:
1. Ask the user for a screenshot of the voucher, the Day Book line, or the dialog.
2. Read the screenshot and compare it with what you posted. Look at the ledger names, the godown, the voucher view
   (invoice or accounting), the tax lines and the party details.
3. Tell the user what differs. Fix the setting with `update_settings` (ledger names, godown, batch, class name) after
   they agree, then preview a single test entry for them to look at before posting the rest.
4. Never delete or alter an existing voucher through the tools. Ask the user to do it in Tally, with the steps.

If you need something this skill does not cover, such as a different kind of entry or a column you do not recognise,
say so and ask the user for a sample and a screenshot of how it should look in Tally.
