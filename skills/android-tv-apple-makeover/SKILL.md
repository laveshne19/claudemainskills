---
name: android-tv-apple-makeover
description: Give an Android TV (Xiaomi, TCL, Sony, Google TV) an Apple TV style home screen and aerial or clock screensaver over wireless ADB, with a safe rollback path and an optional subscription expiry tracker. Use when the user wants to reskin or replace a TV launcher.
origin: community
---

# Android TV Apple TV Makeover

Replace a TV's stock home screen with a tvOS-style launcher, add an Apple-style screensaver with a clock, and install everything over Wi-Fi without a cable. Research is based on public MIT-licensed projects, read from source before recommending them.

## When to Use

- The user wants an Apple TV look on an Android TV or Google TV (Xiaomi PatchWall, TCL, Sony, Hisense, boxes).
- The user wants a faster, ad-free home screen and a photographic or aerial screensaver.
- The user wants to see which streaming subscriptions are close to expiring on the TV.

Do not use for Samsung Tizen, LG webOS or VIDAA sets. They cannot run Android APKs.

## How It Works

### Step 1: Identify the TV before choosing anything

Ask for, or read over ADB, the model code (`ro.product.model`, for example `MiTV-MFTR0`), Android version (`ro.build.version.release`) and whether it runs China firmware (PatchWall, `com.mitv.tvhome`) or Google TV. The launcher build and takeover method depend on these.

Also be clear about panel limits up front: most 55 inch Xiaomi sets are 4K (3840x2160). No software can make a 4K panel show 8K. The best achievable result is vector or 4K artwork rendered natively, which looks crisp on that panel.

### Step 2: Pick a base launcher

Do not write a launcher from scratch. Two mature, MIT-licensed projects exist.

| Project | Strengths | Concerns |
|---|---|---|
| `pengchujin/aerial-tv` | Built for Xiaomi and China-market TVs, ad-free, starts at boot and survives standby, Apple's aerial films in 4K, clock screensaver, phone-based layout editor, Xiaomi models listed as in daily use (MFTR0, MFFU0, MTSU0) | Very broad permissions (`WRITE_SECURE_SETTINGS`, `QUERY_ALL_PACKAGES`, `GET_ACCOUNTS`, `UPDATE_PACKAGES_WITHOUT_USER_ACTION`), contacts the author's own server for updates |
| `lesnolie/Tigris` | Leaner permission set, published SHA-256 checksums, four clock screensaver styles, liquid glass dock | Xiaomi support is weaker; the README lists Xiaomi models with crashes or functional problems and says Xiaomi paths are not comprehensively tested |

Default recommendation for a Xiaomi set: `aerial-tv`. Fall back to Tigris if the TV is Google TV based or the user cares more about a small permission surface.

Star counts on GitHub search results can be inflated. Judge by source, release history and open issues instead.

### Step 3: Read before you run

Third-party installers run with ADB shell power on the TV.

1. Clone the repo into its own empty directory and read the install script end to end.
2. List the hosts it downloads from and the permissions the manifest requests.
3. Download release APKs only from the project's GitHub releases and verify the published SHA-256 when one exists.
4. Show the user the exact `adb` commands before running them.

### Step 4: Enable wireless debugging (user does this on the TV)

Xiaomi: Settings, About, press OK on Model repeatedly to enable developer mode. Then turn on ADB debugging and Install unknown apps (on China firmware this sits under Account and Security). On Google TV based sets use Developer options, Wireless debugging.

Get the TV IP from Settings, Network. Run from a computer on the same Wi-Fi:

```bash
adb connect 192.168.1.20:5555
adb -s 192.168.1.20:5555 get-state
```

Accept the on-screen RSA prompt and choose Always allow.

### Step 5: Install and take over Home

Use the base project's own installer, for example `TV=192.168.1.20 ./install.sh inspect` first, then `install`. Inspect mode reports what would change.

Hard safety rules:

- Never disable `com.mitv.tvhome` (PatchWall) or `com.google.android.tvlauncher` on Xiaomi sets. This can leave a black screen at boot.
- Prefer the project's guard service over disabling system packages. It watches which window is in front and switches back to the new launcher.
- Save the restore commands before changing anything.
- Do not uninstall the stock launcher to work around an install error.

### Step 6: Verify and keep a rollback

Open another app and press the physical Home key. Then check reboot, standby and wake separately. If Home does not return to the new launcher, leave the stock launcher enabled and use the project's `restore` or `repair` mode.

Rollback is always: run the project's `restore` mode, or `adb uninstall <package>`, and the stock home screen returns because it was never disabled.

### Step 7: Subscription expiry tracker (optional)

No streaming app exposes its renewal date to other apps on the TV, so a launcher cannot read it. Netflix, Prime Video, JioHotstar, SonyLIV and the rest keep that data on their servers. Be honest about this with the user. Workable data sources:

| Source | Effort | Accuracy |
|---|---|---|
| Manual entry once (plan, price, renewal date), edited from a phone page | Low | Exact, goes stale if the plan changes |
| Parse renewal and receipt emails from the user's mailbox | Medium, needs explicit user consent to read mail | High |
| Bank or UPI notification parsing | High, privacy heavy | Medium |

Store entries as a small JSON file on the TV. Show a Top Shelf style card per app with days remaining, and colour it amber at 7 days and red at 3 days. Show it on the home screen and on the screensaver clock.

Only read a user's mailbox after they say yes to that specific step.

## Examples

Example request: "Make my Xiaomi 55 inch TV look like Apple TV over Wi-Fi."

1. Read the model and Android version over ADB.
2. Recommend `aerial-tv`, explain the permission trade-off and the 4K panel limit.
3. Clone it into an empty directory, read `install.sh`, show the commands.
4. User enables wireless debugging, you connect and run inspect mode.
5. Install, verify Home, standby and wake, confirm the rollback command works.
6. Offer the subscription tracker and ask which data source they want.

## Anti-patterns

- Running a curl-piped installer you have not read.
- Disabling the stock launcher package to force the default.
- Promising 8K output on a 4K panel.
- Claiming the TV can detect subscription expiry on its own.
- Reading the user's email without a specific yes.
