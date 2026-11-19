---
description: Upload an Excel, CSV or PDF of invoices, bills, notes, receipts or payments and post them into Tally after review
argument-hint: path to the file, and the document type if it is not sales invoices
---
Use the tally-doc-import skill. The file is: $ARGUMENTS

Start with tally_doctor. Then read the file, plan the import, show the table of READY, HELD and DUPLICATE rows, ask the
held questions, and only after the user says go, post the ready rows and report the balance check for each.
