# SpotTransfer: Complete Beginner's Guide

SpotTransfer copies a Spotify playlist into a new private YouTube Music
playlist. It searches for each track, compares title, artist, and album,
handles non-Latin writing systems and reports unmatched tracks.

This guide covers two installation methods:

1. **Fly.io:** the application remains available over the Internet.
2. **Local hosting:** the frontend and backend run only on your computer.

> **Last verified:** June 13, 2026. Prices, promotions, and website interfaces
> may change. Before entering payment details, always check the official pages
> listed under [Official sources](#official-sources).

## Table of Contents

- [How It Works](#how-it-works)
- [Spotify Premium Account](#spotify-premium-account)
- [Create the Spotify App and Credentials](#create-the-spotify-app-and-credentials)
- [Obtain the Spotify Refresh Token](#obtain-the-spotify-refresh-token)
- [Deploy to Flyio](#deploy-to-flyio)
- [Use SpotTransfer](#use-spottransfer)
- [Local Installation](#local-installation)
- [Logs and Troubleshooting](#logs-and-troubleshooting)
- [Security](#security)
- [Advanced Configuration](#advanced-configuration)
- [Reference for People and AI](#reference-for-people-and-ai)
- [Official Sources](#official-sources)

## How It Works

The project contains:

- `frontend/`: the React interface opened in a browser;
- `backend/`: the Python API that reads Spotify and writes to YouTube Music;
- `Dockerfile`: builds the frontend and backend into one image;
- `fly.toml`: configures the Fly.io Machine;
- `scripts/get-spotify-refresh-token.ps1`: a guided Windows script for
  obtaining the Spotify refresh token;
- `nginx.conf`, `supervisord.conf`, and `start-backend.sh`: production startup
  configuration.

Two separate authentication methods are required:

- **Spotify:** Client ID, Client Secret, and refresh token stored on the server.
- **YouTube Music:** browser session headers pasted into the interface by the
  user when starting a clone.

## Spotify Premium Account

### Why Premium is required

New Spotify apps start in **Development mode**. Spotify's official
documentation states that the app owner must have a Spotify Premium account
for a Development-mode app to work.

The current limit is five authenticated Spotify users. Additional users must
be added to the allowlist under **Dashboard > app > Settings > Users
Management**. This SpotTransfer setup normally uses one account: the account
that generates the refresh token.

### Three-month offer

As of June 13, 2026, Spotify's official Italian page advertises:

- Premium Individual at **EUR 0 for three months**;
- **EUR 11.99 per month** afterward;
- only for accounts that have never tried Premium;
- an advertised offer end date of **June 22, 2026**;
- a valid payment method is required.

To activate it:

1. Open <https://www.spotify.com/it/premium/>.
2. Sign in with the account that will own the Spotify Developer app.
3. If the offer is still available and the account is eligible, choose the
   three-month EUR 0 trial.
4. Read the future price, first billing date, and displayed conditions.
5. Enter a valid payment method and confirm.
6. Add the trial end date to your calendar.

Offers vary by country and date. Use the official Premium page for your own
country if you are not in Italy.

### When to cancel without immediately losing Premium

Do not cancel immediately while assuming that the three months will remain
available. Spotify states that cancelling a zero-price free trial moves the
account to Spotify Free **immediately**, and the trial cannot be reactivated.

A cautious process is:

1. Activate the trial.
2. Configure SpotTransfer and complete the required transfers.
3. Wait for Spotify's stated seven-day reminder, while also tracking the date
   yourself.
4. Before renewal, open
   <https://www.spotify.com/account/subscription/manage/>.
5. Select **Cancel subscription** and confirm.
6. Check the account page for the date on which the account will switch to
   Spotify Free.

If the plan was purchased through a mobile operator or another partner, it
must be cancelled through that partner.

## Create the Spotify App and Credentials

### 1. Open the Developer Dashboard

1. Sign in to <https://developer.spotify.com/dashboard> with the Premium
   account.
2. Select **Create app**.
3. Example values:
   - App name: `Personal SpotTransfer`
   - Description: `Personal Spotify to YouTube Music playlist transfer`
4. Accept the developer terms and create the app.

### 2. Configure the redirect URI

Open **Settings** and add exactly:

```text
http://127.0.0.1:8888/callback
```

Save the settings. Do not use `localhost`: Spotify requires an explicit
loopback address such as `127.0.0.1` for local HTTP redirects. Redirects
outside the local computer normally require HTTPS.

### 3. Retrieve the Client ID and Client Secret

On the app page:

1. Copy the **Client ID**.
2. Select **View client secret** and copy the **Client Secret**.
3. Never put them in the repository, screenshots, or public messages.

This project uses the following variable names:

```text
SPOTIPY_CLIENT_ID
SPOTIPY_CLIENT_SECRET
SPOTIFY_REFRESH_TOKEN
```

## Obtain the Spotify Refresh Token

The refresh token lets the backend obtain new access tokens without requiring
a new Spotify login each time.

### Windows: included automated process

Open PowerShell in the main `SpotTransfer` directory, which contains
`Dockerfile` and `fly.toml`.

```powershell
cd "C:\path\where\you\downloaded\SpotTransfer"

.\scripts\get-spotify-refresh-token.ps1 `
  -ClientId "PASTE_CLIENT_ID" `
  -ClientSecret "PASTE_CLIENT_SECRET"
```

The script:

1. displays a Spotify URL;
2. listens on `127.0.0.1:8888`;
3. requests authorization for the `playlist-read-private` scope;
4. receives the callback;
5. prints the refresh token.

Open the displayed URL, authorize the app, and return to PowerShell. Keep the
token in a password manager until it is stored on Fly or in the local `.env`
file.

If PowerShell blocks the script because of its execution policy, allow only
this invocation:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\get-spotify-refresh-token.ps1" `
  -ClientId "PASTE_CLIENT_ID" `
  -ClientSecret "PASTE_CLIENT_SECRET"
```

### macOS or Linux

The included script uses PowerShell's `HttpListener`. The simplest option is
to install PowerShell 7 and run the same file with `pwsh`. Alternatively,
perform the Authorization Code flow described in Spotify's documentation with
the same redirect URI and the `playlist-read-private` scope.

```bash
pwsh ./scripts/get-spotify-refresh-token.ps1 \
  -ClientId "PASTE_CLIENT_ID" \
  -ClientSecret "PASTE_CLIENT_SECRET"
```

## Deploy to Flyio

### What Fly.io is

Fly.io runs the project's Docker image inside a **Machine**, which is a small
virtual machine. `fly deploy` sends the project to a remote builder, builds the
image, and updates the Machine. Secrets are encrypted and injected as
environment variables during startup.

### Costs: important clarification

Fly.io does not provide a permanent free tier to new accounts, and it does not
wait for a "free threshold" before usage starts being billed.

- The free trial includes two total VM hours or seven days, whichever comes
  first.
- Adding a payment card ends the free trial.
- Usage is then metered and billed monthly.
- A small temporary authorization, usually under USD 5, may appear on the
  card. Fly.io describes this as a verification rather than a final charge.
- Fly.io currently does not provide automatic budget alerts.

This configuration uses one `shared-cpu-1x` Machine with 512 MB and
`min_machines_running = 1`. Keeping one Machine active prevents an in-progress
background clone from being interrupted. Usage may cost several dollars per
month plus any applicable network traffic. Check the current price with the
[Fly calculator](https://fly.io/calculator) and monitor **Current month to date
bill** in the dashboard.

This configuration does not create databases, persistent volumes, or a
dedicated IPv4 address.

### 1. Create a Fly.io account

1. Open <https://fly.io/app/sign-up>, or run `fly auth signup` after installing
   the CLI.
2. Confirm the email address and account.
3. Use the initial trial or add a payment method under **Billing**.
4. If you add a card, immediately review current pricing and usage.

Without a card, apps stop when the trial ends. Fly.io also permits purchasing
credits, with a documented minimum purchase of USD 25. Prepaid cards cannot be
saved as the default payment method, but may be used to purchase credits.

### 2. Install flyctl

#### Windows PowerShell

```powershell
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

If `pwsh` is unavailable:

```powershell
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

Close and reopen PowerShell, then verify the installation:

```powershell
fly version
```

#### macOS

```bash
brew install flyctl
fly version
```

#### Linux

```bash
curl -L https://fly.io/install.sh | sh
fly version
```

### 3. Sign in from the CLI

```powershell
fly auth login
```

The browser opens to complete authentication. To create an account from the
CLI instead, run:

```powershell
fly auth signup
```

### 4. Open the correct directory

Run all following commands from the `SpotTransfer` project root:

```powershell
cd "C:\path\where\you\downloaded\SpotTransfer"
Get-ChildItem
```

You should see at least `Dockerfile`, `fly.toml`, `backend`, and `frontend`.

On macOS/Linux:

```bash
cd /path/to/SpotTransfer
ls
```

### 5. Choose a unique name

The Fly app name becomes part of `https://NAME.fly.dev` and must be globally
unique. Open `fly.toml` and change its first line:

```toml
app = "spottransfer-unique-name"
```

Use only lowercase letters, numbers, and hyphens. Replace
`spottransfer-unique-name` in the following examples with your chosen name.

### 6. Create the Fly app without deploying yet

```powershell
fly apps create spottransfer-unique-name
```

Check it:

```powershell
fly status -a spottransfer-unique-name
```

If the name is already taken, choose another one, update `fly.toml`, and repeat
the command.

### 7. Set the secrets quickly

Run one PowerShell command:

```powershell
fly secrets set -a spottransfer-unique-name `
  SPOTIPY_CLIENT_ID="PASTE_CLIENT_ID" `
  SPOTIPY_CLIENT_SECRET="PASTE_CLIENT_SECRET" `
  SPOTIFY_REFRESH_TOKEN="PASTE_REFRESH_TOKEN"
```

On macOS/Linux:

```bash
fly secrets set -a spottransfer-unique-name \
  SPOTIPY_CLIENT_ID="PASTE_CLIENT_ID" \
  SPOTIPY_CLIENT_SECRET="PASTE_CLIENT_SECRET" \
  SPOTIFY_REFRESH_TOKEN="PASTE_REFRESH_TOKEN"
```

Verify the secret names:

```powershell
fly secrets list -a spottransfer-unique-name
```

Fly displays names and digests, never plaintext values. Setting a secret
restarts the app's Machines. Do not place these values in `fly.toml`, because
that file is source code and may be published on GitHub.

### 8. Verify the build without publishing

This step is optional but recommended:

```powershell
fly deploy --build-only --remote-only -a spottransfer-unique-name
```

The Dockerfile also runs the matcher's automated tests.

### 9. Perform the first deployment

```powershell
fly deploy -a spottransfer-unique-name
```

The first build may take several minutes. When it finishes:

```powershell
fly status -a spottransfer-unique-name
fly apps open -a spottransfer-unique-name
```

The address will look like:

```text
https://spottransfer-unique-name.fly.dev
```

### 10. Later deployments

After modifying the code, return to the project root:

```powershell
cd "C:\path\to\SpotTransfer"
fly deploy -a spottransfer-unique-name
```

### 11. View server logs

Live logs:

```powershell
fly logs -a spottransfer-unique-name
```

Press `Ctrl+C` to stop viewing logs without stopping the server.

Only logs already present in the buffer:

```powershell
fly logs --no-tail -a spottransfer-unique-name
```

Other useful checks:

```powershell
fly status -a spottransfer-unique-name
fly machine list -a spottransfer-unique-name
fly releases -a spottransfer-unique-name
fly dashboard -a spottransfer-unique-name
```

### 12. Stop ongoing costs

Delete the app when it is no longer needed:

```powershell
fly apps destroy spottransfer-unique-name
```

Read the confirmation carefully and enter the requested app name. Also check
the Fly dashboard to ensure there are no other apps, volumes, or managed
services. This project does not require volumes or databases.

## Use SpotTransfer

### 1. Prepare the Spotify playlist

Use a public playlist owned by the account that generated the refresh token,
or a playlist on which that account is a collaborator. Copy its URL in this
format:

```text
https://open.spotify.com/playlist/...
```

### 2. Copy the YouTube Music headers

These headers represent the YouTube Music session and are sensitive.

1. Sign in to <https://music.youtube.com>.
2. Open Developer Tools:
   - Windows/Linux: `Ctrl+Shift+I`
   - macOS: `Command+Option+I`
3. Open the **Network** tab.
4. Search for `/browse`.
5. If nothing appears, open **Library** or scroll the page.
6. Select a request with method `POST` and status `200`.
7. Firefox: right-click and select **Copy > Copy request headers**.
8. Chrome/Edge: open **Headers** and copy **Request Headers**, or use **Copy as
   fetch** and retain the required headers.
9. Paste them into SpotTransfer's **Paste headers here** field.

Never publish headers containing `Authorization` or `Cookie`. If you sign out
of YouTube Music, you may need to copy fresh headers.

### 3. Clone the playlist

1. Select **Connect**.
2. Paste the Spotify URL and YouTube Music headers.
3. Select **Clone Playlist**.
4. Wait. Large playlists and retries may take several minutes.
5. Review any unmatched tracks.

## Local Installation

Local hosting does not require Fly.io and has no hosting cost. The computer
must remain powered on while the application is being used.

### Programs to install

- **Git:** <https://git-scm.com/downloads>
- **Python:** <https://www.python.org/downloads/>
- **Node.js LTS:** <https://nodejs.org/en/download>
- Chromium, Chrome, Edge, or Firefox.

The Dockerfile uses Node 22. For local development, use Node 22 LTS or a newer
compatible LTS release. Verify the installations:

```powershell
git --version
python --version
node --version
corepack --version
```

On Windows, if `python` opens Microsoft Store instead of the interpreter,
install Python from the official website or Python Install Manager, then
reopen the terminal.

### 1. Download the project

If the repository is hosted on GitHub:

```powershell
git clone YOUR_REPOSITORY_URL.git
cd SpotTransfer
```

If the folder already exists, open PowerShell directly in `SpotTransfer`.

### 2. Prepare the Python backend

#### Windows PowerShell

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

#### macOS/Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

### 3. Fill in `backend/.env`

Open `backend/.env` and enter:

```env
SPOTIPY_CLIENT_ID=PASTE_CLIENT_ID
SPOTIPY_CLIENT_SECRET=PASTE_CLIENT_SECRET
SPOTIFY_REFRESH_TOKEN=PASTE_REFRESH_TOKEN
SPOTIFY_MARKET=IT
FRONTEND_URL=http://localhost:5173
```

Do not add quotation marks unless they are part of the value. Never commit
`.env` to Git.

### 4. Test and start the backend

While still inside `backend`, with the virtual environment active:

```powershell
python -m unittest discover -s tests
python main.py
```

Leave this terminal open. The backend listens at:

```text
http://localhost:8080
```

Quick check from a second PowerShell terminal:

```powershell
Invoke-RestMethod http://localhost:8080/
```

The expected response contains `Server Online`.

### 5. Prepare the frontend

Open a **second terminal** in the project directory:

```powershell
cd "C:\path\to\SpotTransfer\frontend"
corepack enable
corepack prepare pnpm@9.15.4 --activate
pnpm install --frozen-lockfile
Copy-Item .env.example .env
pnpm dev
```

On macOS/Linux, replace `Copy-Item` with:

```bash
cp .env.example .env
```

`frontend/.env` must contain:

```env
VITE_API_URL=http://localhost:8080
```

Open <http://localhost:5173>.

### 6. Stop local hosting

Press `Ctrl+C` in both the frontend and backend terminals. Exit the Python
virtual environment with:

```powershell
deactivate
```

### Local Docker alternative

If Docker Desktop is installed, build the same image used by Fly:

```powershell
docker build -t spottransfer-local .
docker run --rm -p 8080:8080 `
  -e SPOTIPY_CLIENT_ID="PASTE_CLIENT_ID" `
  -e SPOTIPY_CLIENT_SECRET="PASTE_CLIENT_SECRET" `
  -e SPOTIFY_REFRESH_TOKEN="PASTE_REFRESH_TOKEN" `
  -e FRONTEND_URL="http://localhost:8080" `
  spottransfer-local
```

Open <http://localhost:8080>. Never put real credentials in a `Dockerfile` or
Docker image.

## Logs and Troubleshooting

### Spotify returns `403 Forbidden`

Check the following in order:

1. The Developer app owner has an active Premium subscription.
2. The refresh token was generated by the same app as the Client ID and Client
   Secret.
3. The refresh-token account owns or can collaborate on the playlist.
4. If another user is used in Development mode, that user is in Spotify's
   allowlist.

### `Invalid refresh token`

The value may be a temporary access token or may belong to another app. Run
the script again with the correct Client ID and Client Secret. If Spotify does
not return a new refresh token, revoke the app from the Spotify account page
and authorize it again.

### YouTube Music authentication failed

Copy fresh headers from a request with:

- domain `music.youtube.com`;
- method `POST`;
- path `/browse`;
- status `200`;
- an authenticated YouTube Music session.

### Tracks are not found

The matcher searches both `songs` and `videos`, applies a confidence threshold,
and transliterates many writing systems. Do not immediately lower the
threshold, because that increases the risk of adding the wrong song. Check the
logs for the best score found.

### Temporary error while adding playlist items

YouTube Music may occasionally return an empty or non-JSON response after
receiving a write. SpotTransfer writes in blocks, retries temporary failures,
and rereads the playlist before retrying so that an already accepted block is
not duplicated. The default block size is 50 items.

### Fly build failed

```powershell
fly deploy --build-only --remote-only -a spottransfer-unique-name
```

Read the first `ERROR` line, not only the final line. Also check:

```powershell
fly status -a spottransfer-unique-name
fly logs --no-tail -a spottransfer-unique-name
fly secrets list -a spottransfer-unique-name
```

### The app is slow on first access

With `min_machines_running = 1`, the Machine should remain active. If this is
changed to `0`, Fly may stop the Machine when idle, and the next request must
start it again. Do not choose `0` without considering that SpotTransfer runs
background jobs.

## Security

- Never commit `.env`, the Client Secret, refresh token, or YouTube headers.
- Never paste secrets into public GitHub issues, chats, or screenshots.
- Fly secrets are encrypted and their values cannot be read back through the
  CLI.
- Anyone able to deploy code to the app could modify it to print secrets, so
  restrict access to the Fly project.
- If the Client Secret is exposed, use **Rotate** in the Developer Dashboard
  and update the Fly secrets.
- If YouTube headers are exposed, sign out affected Google sessions and obtain
  fresh headers.
- Cloning uses personal APIs and sessions. Respect platform terms, copyright,
  and privacy requirements.

## Advanced Configuration

Optional environment variables:

```text
YTMUSIC_MIN_MATCH_SCORE=0.70
YTMUSIC_SEARCH_FILTERS=songs,videos
YTMUSIC_SEARCH_DELAY_SECONDS=0.75
YTMUSIC_SEARCH_RETRIES=3
YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE=50
YTMUSIC_PLAYLIST_ADD_RETRIES=5
YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS=10
SPOTIFY_MARKET=IT
SPOTTRANSFER_JOB_REUSE_SECONDS=900
SPOTTRANSFER_JOB_TTL_SECONDS=86400
```

Fly example:

```powershell
fly secrets set -a spottransfer-unique-name `
  YTMUSIC_SEARCH_DELAY_SECONDS="1.25"
```

Transliteration is only an additional variant. The original text always
remains available to the matcher. Japanese uses Hepburn romanization;
Cyrillic, Greek, Chinese, Korean, Arabic, Hebrew, Indic scripts, Thai, and
other writing systems use general Unicode transliteration.

## Reference for People and AI

This section summarizes the intended configuration in an unambiguous format.

### Objective

```text
Input:
- Spotify playlist URL
- authenticated YouTube Music headers

Server credentials:
- SPOTIPY_CLIENT_ID
- SPOTIPY_CLIENT_SECRET
- SPOTIFY_REFRESH_TOKEN

Output:
- private YouTube Music playlist
- missed_tracks list
```

### Ports and URLs

```text
Development frontend: http://localhost:5173
Development backend:  http://localhost:8080
Production nginx:     internal/public port 8080
Production API:       /api/* -> Gunicorn backend at 127.0.0.1:5000
Health check:         /health
```

### Minimum Fly commands

```text
fly auth login
fly apps create APP_NAME
fly secrets set -a APP_NAME SPOTIPY_CLIENT_ID=... SPOTIPY_CLIENT_SECRET=... SPOTIFY_REFRESH_TOKEN=...
fly deploy -a APP_NAME
fly status -a APP_NAME
fly logs -a APP_NAME
fly apps open -a APP_NAME
```

### Minimum local commands

```text
Backend:
cd backend
python -m venv .venv
activate .venv
python -m pip install -r requirements.txt
create backend/.env
python main.py

Frontend:
cd frontend
corepack enable
corepack prepare pnpm@9.15.4 --activate
pnpm install --frozen-lockfile
create frontend/.env
pnpm dev
```

### Constraints that require verification before changing

- Spotify redirect URI: `http://127.0.0.1:8888/callback`.
- Do not use `localhost` as the Spotify redirect URI.
- The Spotify app owner needs Premium in Development mode.
- The production frontend uses `VITE_API_URL=/api`.
- The Fly backend uses one Machine/worker because job state is local.
- Job files are ephemeral and stored under `/tmp`.
- Do not store YouTube headers as a global secret. They belong to the user
  session that starts each job.

## Official Sources

Consulted on June 13, 2026:

- [Spotify Premium Italy](https://www.spotify.com/it/premium/)
- [Spotify: cancel Premium](https://support.spotify.com/it/article/cancel-premium/)
- [Spotify Web API: quota modes and Premium requirement](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)
- [Spotify Web API: creating an app](https://developer.spotify.com/documentation/web-api/concepts/apps)
- [Spotify Web API: redirect URIs](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
- [ytmusicapi: browser authentication](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)
- [Fly.io: install flyctl](https://fly.io/docs/flyctl/install/)
- [Fly.io: quickstart and deployment](https://fly.io/docs/getting-started/launch/)
- [Fly.io: secrets](https://fly.io/docs/apps/secrets/)
- [Fly.io: logs](https://fly.io/docs/flyctl/logs/)
- [Fly.io: free trial](https://fly.io/docs/about/free-trial/)
- [Fly.io: billing](https://fly.io/docs/about/billing/)
- [Fly.io: pricing](https://fly.io/docs/about/pricing/)
- [Fly.io: cost management](https://fly.io/docs/about/cost-management/)
- [Python on Windows](https://docs.python.org/3/using/windows.html)
- [Download Node.js LTS](https://nodejs.org/en/download)
- [Download Git](https://git-scm.com/downloads)
