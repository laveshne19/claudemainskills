# Install

You need a Windows PC that runs TallyPrime (Silver or Gold), and Claude (Desktop or Claude Code) on the same PC.
Python 3.10 or newer is installed for you if it is missing.

## Desktop app (recommended for the first test)

1. Unzip `TallyConnect-Desktop-0.2.0.zip` anywhere on the PC that has Tally.
2. Double click `INSTALL.bat` once.
3. Double click `Start Demo (no Tally needed).bat` to try it, then `Start Tally Connect.bat` for your real Tally.
`READ-ME-FIRST.txt` in the zip has the same steps in short.

## The easy way (Claude connection)

1. Download or clone this folder.
2. Open PowerShell in the folder and run:
   ```
   powershell -ExecutionPolicy Bypass -File installer\install.ps1
   ```
3. When it asks, open Tally, load your company, and set it to Server mode (steps in `TALLY-SETUP.md`). Press Enter.
4. Fully quit Claude, including from the system tray, and open it again.
5. Start a **new** chat and type: `check the Tally connection`.

A resumed old chat does not load new tools. Always use a new chat after installing.

## Add the skills (recommended)

The skills teach Claude the routine and the safety rules. In Claude Code:

```
claude plugin marketplace add C:\path\to\this\folder
claude plugin install tally-connect@neural-desk
```

In Claude Desktop, use Customize, Plugins, and upload the `plugin` folder as a zip.

## By hand

```
pip install .
claude mcp add tally-connect -- tally-connect-mcp
```

For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{ "mcpServers": { "tally-connect": { "command": "tally-connect-mcp" } } }
```

## Check it

```
tally-connect doctor
```

## If Tally is on a different PC

Install Tally Connect on the PC where Claude runs, and set the Tally PC address in `%USERPROFILE%\.tally-connect\config.json`:
`{ "host": "192.168.1.30", "port": 9000 }`. On the Tally PC, allow tally.exe through the Windows firewall for Domain, Private
and Public networks. Test with `Test-NetConnection 192.168.1.30 -Port 9000`.

## Update or remove

Update: run the installer again. Remove: `pip uninstall tally-connect` and delete `%USERPROFILE%\.tally-connect`.
