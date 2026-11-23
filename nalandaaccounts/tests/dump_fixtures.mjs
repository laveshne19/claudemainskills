// Prints the fictional ledgers as JSON so the Python tests use exactly the same data as the portal tests.
import { makeLedgers } from "./fixtures.mjs";
process.stdout.write(JSON.stringify(makeLedgers({ today: "2026-09-30" })));
