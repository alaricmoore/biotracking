# Remote Access Guide — sardinetracker

## Read This First

This document describes how to access sardine-track from outside your local network — from your phone on cellular, from work, from anywhere.

Before you do any of this, understand what you are doing:

**Anything connected to the internet is dangerous and insecure. The most secure place for your health data is in your own head with a tight lip. A faraday cage helps too.**

The default sardine-track setup runs on localhost. Nothing leaves your computer. Nobody can reach it but via physical access to that machine, *on* that machine, on *that* network. That is the safest possible configuration and it is sufficient for most people.

This guide exists for people who understand the risk surface and want remote access anyway. If you are not comfortable with concepts like VPNs, reverse proxies, open ports, and what it means to expose a service to the internet, stop here. Use the local setup. It is genuinely good enough; for the gap between the doctor's waiting room or the ER for four hours and getting home to your own network, travel with a notebook. Seriously, it's great therapy and also provides notes for future-you when you want to log the whole thing in sardine-track.

If you proceed, you accept that you are responsible for the security of your own data. The author of this software is not responsible for data exposure resulting from network configuration choices you make.

---

## What "Less Internet" Means and Doesn't Mean

There is no such thing as "connected to the internet but safe." There is only a spectrum of exposure.

The setups described in this guide are:

- More secure than a public URL with no auth
- More secure than port forwarding your router
- Not as secure as local only
- Not as secure as not having the data digitally at all

Proceed accordingly.

---

## Two Paths

There are two patterns documented here. Pick the one that fits your stomach and your wallet.

| | **Option A: Cloudflare Tunnel** | **Option B: Tailscale + cloud VPS** |
|---|---|---|
| **What you need** | A domain you own + free Cloudflare account | A Tailscale account + a small cloud VPS (any provider) |
| **Router config** | None | None |
| **Public IP needed?** | No | No (the VPS provides one) |
| **Cost** | ~$10/yr for the domain; tunnel is free | $0–$15/mo VPS depending on provider |
| **HTTPS** | Automatic at Cloudflare's edge | You set up Let's Encrypt yourself |
| **DDoS / abuse protection** | Built in (Cloudflare) | None (your VPS) |
| **Traffic path** | You → Cloudflare edge → tunnel → Pi | You → VPS → Tailscale → Pi |
| **Trust surface** | Cloudflare can see your domain's traffic flow (not contents) | Your VPS provider sees encrypted Tailscale traffic |
| **Friction** | Lower once set up; CF dashboard is polished | More moving parts, but no third-party between you and your traffic |

**Option A is what the author runs now.** It moved off Option B after Oracle Cloud unceremoniously shut down the free-tier VM without warning, which is a useful data point about depending on free-tier VPS plans.

If you don't want to own a domain or trust Cloudflare, Option B is still a fine setup.

---

## Option A: Cloudflare Tunnel

### How it works

```
Your phone / laptop (anywhere)
        |
        | (HTTPS over the public internet)
        |
Cloudflare edge (terminates TLS, serves your custom domain)
        |
        | (encrypted tunnel established by cloudflared running on the Pi)
        |
Raspberry Pi (your home network, running sardine-track on localhost)
```

The Pi does not need a public IP. It does not need any router ports forwarded. A small daemon called `cloudflared` runs on the Pi and makes an *outbound* connection to Cloudflare's edge. When you visit `app.yourdomain.com`, Cloudflare routes the request down that tunnel to your Flask app on the Pi.

Your database never leaves the Pi.

### What you need

- A Raspberry Pi (any model capable of running Python 3.9+, a Pi 4 or newer is comfortable. But if you want to get weird with it, host it on Plan 9 inside a gameboy color. I'll buy you lunch.)
- A domain name — buy via Cloudflare Registrar (cheapest, no markup) or transfer an existing one. ~$10/yr for `.com`, less for some TLDs.
- A free Cloudflare account
- Basic comfort with SSH and the Linux command line (`man -k` is your friend)

### Step 1: Get sardine-track running on the Pi

Follow the standard installation instructions in the README. Verify it runs on `http://localhost:5000` from the Pi itself before touching any networking. If you don't have a keyboard or screen, install headless debian onto the pi and ssh into it. You don't need a UI for any of this.

The Flask app should keep listening on `127.0.0.1` (localhost). Unlike the Tailscale path, you do **not** need to change it to `0.0.0.0` — the tunnel runs on the Pi itself and reaches Flask via localhost.

### Step 2: Add your domain to Cloudflare

1. Sign up at [cloudflare.com](https://cloudflare.com)
2. Add your domain. If you bought it through Cloudflare Registrar, this is automatic. If it's at another registrar, Cloudflare gives you two nameservers to set there — propagation usually takes under an hour.
3. Confirm your domain shows "Active" status in the Cloudflare dashboard.

### Step 3: Open the Zero Trust dashboard

Cloudflare Tunnel lives under their Zero Trust product. Go to [one.dash.cloudflare.com](https://one.dash.cloudflare.com) (recent accounts serve the same console at `dash.cloudflare.com/<account-id>/one/`). First time through, Zero Trust asks you to pick a team name and choose a plan — take **Free**. It will still walk you through payment details on the free tier and won't charge you.

### Step 4: Create a tunnel

1. In Zero Trust, go to **Networks → Tunnels**
2. Click **Create a tunnel**, choose **Cloudflared** as the connector type
3. Name it something memorable like `home-pi` or `the-fish-tank`
4. Cloudflare gives you a one-line install command for your platform. For Raspberry Pi (64-bit OS), it looks like:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
sudo cloudflared service install <YOUR_LONG_TOKEN>
```

Copy the command Cloudflare shows you — it includes the token specific to your tunnel. Run it on the Pi. The `service install` step registers cloudflared as a systemd service, so it starts on boot and restarts if it crashes.

Back in the dashboard, you should see the connector appear as **Healthy** within a few seconds.

### Step 5: Route your subdomain to the tunnel

Still in the tunnel config, switch to the **Public Hostnames** tab. Add a hostname:

- **Subdomain**: `app` (or whatever you want — `track`, `sardines`, your call)
- **Domain**: pick your domain from the dropdown
- **Service type**: `HTTP`
- **URL**: `localhost:5000`

Save. Cloudflare automatically creates the DNS record. Within seconds, `https://app.yourdomain.com` should serve your Flask app — with a valid HTTPS certificate, terminated at Cloudflare's edge.

### Step 6: Verify

From your phone on cellular (not your home WiFi — that's the whole point), visit `https://app.yourdomain.com`. You should see the sardine-track login page. Log in, poke around. If it works, you're done with the network side.

### Optional: add Cloudflare Access on top

Sardine-track has its own login, but that's one password facing the open internet. **Cloudflare Access** adds a second gate at Cloudflare's edge, in front of the tunnel: visitors prove who they are before a request ever reaches the Pi. Your Flask login is untouched and still applies — Access sits in front of it.

Access binds to a *hostname*, not to a server. Your tunnel already answers "where does this traffic go", so there is no IP, port, or protocol to enter here. If a setup wizard asks you for those, you're in the flow for people who don't have a tunnel yet — back out of it.

#### Read this first: three kinds of traffic share one hostname

```
                app.yourdomain.com  (Cloudflare edge)
                            |
    +-----------------------+-----------------------+
    |                       |                       |
/portal/*                /api/*            everything else
clinicians          phone + wearable         you, a browser
token in the URL       bearer token           Flask login
    |                       |                       |
 BYPASS                  BYPASS              ALLOW + MFA
    +-----------------------+-----------------------+
                            |
                    Cloudflare Tunnel
                            |
                      Pi -> Flask :5000
```

Gating the whole hostname in one click breaks two of those three. Clinician portal links would land on a Cloudflare login page instead of the record, and the phone sync plus the UV wearable would get an HTML redirect where they expect JSON. Neither failure is loud — you find out when a doctor emails you, or when a week of wearable data turns out to be missing.

Access resolves overlapping rules by **most-specific-path-wins**, so carve out the two machine-and-token lanes first, then gate everything else. Build them in that order and there's never a window where the portal is dark.

#### Step 1: Onboard to Zero Trust

Access lives in a separate console from your domain dashboard. The Access page you'll find under your domain is an advert for it, not the product. Go to [one.dash.cloudflare.com](https://one.dash.cloudflare.com) (recent accounts serve the same console at `dash.cloudflare.com/<account-id>/one/`).

First time through you'll pick a **team name** — it becomes `<teamname>.cloudflareaccess.com`, the host that serves your login page and sends your PIN emails. Pick something you'd recognize half-asleep; it's how you tell a real Access prompt from a phished one. Accept the auto-generated name and you'll get a random one like `quiet-harbor-4f21` instead.

You'll also be asked for a plan. Choose **Free**. Cloudflare still walks you through payment details on the free tier and won't charge you; this setup uses one of the 50 free seats.

#### Step 2: Turn on a login method

**Integrations → Identity providers → Add new → One-time PIN.** Nothing to configure. Access emails you a single-use code that expires in 10 minutes.

#### Step 3: Create the open lane — do this one first

**Access controls → Applications → Add an application → Self-hosted.** Name it `sardine-open`.

Under **Destinations**, add two public hostnames. One application can hold many destinations, and its policy applies to all of them — which is exactly what you want here, since both lanes need the same rule:

| Subdomain | Domain | Path |
|-----------|--------------|------------|
| `app` | `yourdomain.com` | `portal/*` |
| `app` | `yourdomain.com` | `api/*` |

Leave off the leading slash; the UI supplies it. Then **Create new policy** → Action **Bypass** → Include → **Everyone**, and save. (The Action selector is inside the policy form, not on the application page.)

Bypass means Access doesn't inspect these paths at all. That is not a downgrade: portal links are already gated by an unguessable token that you can revoke and that expires, and every `/api/` route either checks a bearer token or is `@login_required`. They end up exactly as protected as they were before you added Access.

Note that `portal/*` matches `/portal/<token>` but **not** `/portals`, your link-management page — the wildcard sits after a slash. That's deliberate, and worth verifying in Step 6 rather than assuming.

#### Step 4: Gate everything else

A second self-hosted application, named `sardine`. One destination: subdomain `app`, domain `yourdomain.com`, **Path empty**. Empty path means the whole hostname.

Policy → Action **Allow** → Include → **Emails** → your address. Set the session duration long — a month — so you aren't re-authenticating daily.

If a setup wizard already created an application for you, check the policy it generated before you attach a hostname to it. It guesses at your email, and a wrong guess locks you out of your own app.

#### Step 5: Add a real second factor

Identity providers are alternative ways to prove *who* you are. Enabling two of them (say, one-time PIN and a Cloudflare account) gives you two front doors, not a door and a deadbolt — an attacker takes whichever is weaker. If you stop here, your real second factor is whatever protects your email account.

For an explicit second factor, use **Independent MFA** — Cloudflare enforces it itself, so you don't need a Google or Okta account in the loop:

1. **Access controls → Access settings** → enable Independent MFA and tick the methods you'll accept: authenticator app (TOTP), security key, or biometrics (Touch ID, Face ID, Windows Hello). This is the organization-wide switch.
2. On the `sardine` application → **Authentication → MFA** tab → **Custom MFA settings**. Choose which of those methods this application accepts, and set **Authentication duration** — how often Access re-challenges you. "Require every login" is the strict setting; every 24 hours is a reasonable middle if you gave the application a long session duration in Step 4.
3. Enroll your own device: sign in at `<teamname>.cloudflareaccess.com` → Account settings → **MFA devices**.

Note the direction of travel between those first two steps. The application's MFA tab can only *narrow* what the organization already allows — it can't add a method. If that tab offers you nothing selectable, step 1 isn't done.

Enroll while you still have a working session, and keep that browser open until a *second*, private window has logged in and cleared the MFA prompt. You are probably the only administrator on this account, so there is nobody to let you back in.

#### Step 6: Verify every lane before you trust it

Check each lane from something with no cookies and no session — a private window, or curl from a different machine. A setup that's wrong in one lane looks completely fine from the lane you happen to test.

```bash
APP=https://app.yourdomain.com
curl -s -o /dev/null -w 'root      %{http_code} %{redirect_url}\n' $APP/
curl -s -o /dev/null -w 'portals   %{http_code}\n' $APP/portals
curl -s -o /dev/null -w 'portal    %{http_code}\n' $APP/portal/badtoken
curl -s -w '\nsync      %{http_code}\n' -X POST -H 'Content-Type: application/json' \
     -d '{}' $APP/api/health-sync
```

| Request | Expect | What it proves |
|---------|--------|----------------|
| `/` | 302 to `<teamname>.cloudflareaccess.com` | the gate is live |
| `/portals` | 302 to Access | management page is gated — the wildcard didn't leak |
| `/portal/badtoken` | **403** from sardine-track | bypass works; traffic reached the Pi |
| `POST /api/health-sync` | **401** `{"error":"unauthorized"}` | bypass works; bearer auth still enforced |

One quirk that looks like a failure and isn't: a **GET** on `/api/health-sync` redirects to `/login` rather than returning 401. That's sardine-track's own `require_login`, which sees `request.endpoint` as `None` on a 405 method mismatch. The POST path — the one your phone and wearable actually use — returns clean JSON. Test with POST.

**Three things curl cannot tell you.** MFA fires *after* identity, behind the login — from the outside, a gate with MFA and a gate without it are byte-identical. That's the point of it, and it's also why you have to check these by hand:

- Click a real portal link and confirm the record still renders. A 403 on a bad token proves traffic reaches the Pi; only a live token proves the page still draws.
- Sign in from a private window. You should hit, in order: the Access login → your PIN or identity provider → **an authenticator challenge** → *then* the sardine-track Flask login. If that third step doesn't appear and you land straight on the Flask login, MFA is configured but not enforcing — check the organization switch and the Authentication duration.
- Confirm your phone actually completes a sync, rather than trusting the 401 above. The 401 proves Access let the request through to Flask; it doesn't prove your token is still right.

### Sardine-track sees Cloudflare IPs, not real user IPs

Behind a Cloudflare tunnel, `request.remote_addr` in Flask is a Cloudflare edge IP, not the actual visitor's IP. If you need the real client IP (for logging, rate limiting, etc.), Cloudflare passes it in the `CF-Connecting-IP` header. Flask doesn't read it by default; for sardine-track's purposes (a personal app with login) you likely don't need to bother.

---

## Option B: Tailscale + a cloud VPS

This is the original setup. It works without owning a domain (you can use the VPS's raw IP), at the cost of needing a small cloud server somewhere.

### How it works

```
Your phone / laptop (anywhere)
        |
        | (HTTPS to the VPS's public IP)
        |
Cloud VPS (public IP, runs nginx as reverse proxy, runs Tailscale)
        |
        | (Tailscale encrypted tunnel)
        |
Raspberry Pi (your home network, runs Tailscale + sardine-track)
        |
        | (localhost)
        |
sardine-track app + SQLite database
```

Your database never leaves the Raspberry Pi. The VPS sees only encrypted Tailscale traffic — it cannot read the contents. Your phone connects to the VPS's public IP, which proxies through Tailscale to the Pi.

### What you need

- A Raspberry Pi (see notes above)
- A Tailscale account (free tier is sufficient)
- A small cloud VPS — any provider works. Hetzner CX11 (~$4/mo), DigitalOcean droplet (~$6/mo), Linode nanode (~$5/mo) are all fine. Oracle's "always-free" tier *technically* works but the author had her free VM shut down without warning, so plan for that possibility if you go that route.
- A DNS name if you want a human-readable URL (optional)
- Basic comfort with SSH and the Linux command line
- Starlink or any ISP — this setup works without a static public IP at home, which is the point

### Step 1: Install sardine-track on the Raspberry Pi

Same as Option A — get it running on `http://localhost:5000` first. For this path, you'll need to change the bind address in step 6 below.

### Step 2: Install Tailscale on the Raspberry Pi

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Follow the authentication link. The Pi will appear in your Tailscale admin console with a Tailscale IP (usually in the `100.x.x.x` range).

### Step 3: Provision your cloud VPS

Pick a provider, spin up the smallest VM they offer running Ubuntu 22.04 LTS (or whatever Debian-family OS you prefer). Note the public IP. Don't lose your SSH key.

SSH in and install Tailscale on the VPS too:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Both the Pi and the VPS should now appear in your Tailscale admin console.

### Step 4: Configure the VPS as a reverse proxy

Install nginx on the VPS:

```bash
sudo apt update && sudo apt install nginx -y
```

Create a config at `/etc/nginx/sites-available/sardinetrack`:

```nginx
server {
    listen 80;
    server_name YOUR_VPS_PUBLIC_IP;

    # Basic auth is strongly recommended — see security notes below
    # auth_basic "sardinetrack";
    # auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://YOUR_PI_TAILSCALE_IP:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Replace `YOUR_VPS_PUBLIC_IP` and `YOUR_PI_TAILSCALE_IP` with the actual values.

Enable the config:

```bash
sudo ln -s /etc/nginx/sites-available/sardinetrack /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 5: Open the firewall on the VPS

Open port 80 (and 443 if you add HTTPS):

```bash
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

If your provider has a separate cloud-level firewall (Oracle did, AWS does), open those ports in their console too.

### Step 6: Start sardine-track on the Pi listening on Tailscale's interface

By default sardine-track listens on `127.0.0.1` only. To accept Tailscale traffic from the VPS, edit `app.py` and change:

```python
host='127.0.0.1'
```

to:

```python
host='0.0.0.0'
```

Restart the app. You should now be able to reach it from your VPS's public IP. And if you dig around the Tailscale options you can even give your Pi a nifty easy-remember-name.

**Keep it running:**
Use systemd, screen, or tmux so the app doesn't die when you close SSH:

```bash
screen -S sardinetrack
python3 app.py
# Ctrl+A, D to detach
```

### Tailscale Funnel — a third option, briefly

Tailscale offers a feature called **Funnel** that lets you expose a tailnet service to the public internet *without* a separate VPS. It uses Tailscale's edge as the public-facing layer. As of writing it's free for personal use with limits.

It's a reasonable middle ground if you want to skip the VPS but don't want Cloudflare in the loop. Setup is essentially: `tailscale funnel 5000` on the Pi. Their docs cover it well.

---

## Security Notes — Please Read These (apply to both options)

### Use a strong password on sardine-track itself

Whichever path you choose, sardine-track's own login is the last line of defense. Use a real password — long, unique, not your email password, not your phone PIN.

### Add another auth layer if you can

- **Option A**: Cloudflare Access (free) — an identity gate at Cloudflare's edge in front of the Flask login, with optional authenticator-app MFA. See [Optional: add Cloudflare Access on top](#optional-add-cloudflare-access-on-top) above; it needs path carve-outs for `/portal/*` and `/api/*` or it will break clinician links and device sync.
- **Option B**: nginx basic auth (the commented lines in the config above) — uncomment them, then:

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd yourname
```

### HTTPS

- **Option A**: handled automatically by Cloudflare at the edge.
- **Option B**: you need to set this up yourself. Get a domain pointed at the VPS, then:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
```

Without HTTPS on Option B, your health data travels in plaintext between your phone and the VPS. Tailscale encrypts the VPS-to-Pi leg, not the you-to-VPS leg.

### Keep software updated

```bash
sudo apt update && sudo apt upgrade -y
```

Run this on the Pi (and, for Option B, on the VPS) regularly. Unpatched software is how things go wrong.

### Understand your Tailscale ACLs (Option B only)

By default Tailscale allows all devices in your network to talk to each other. Review your ACL settings in the Tailscale admin console and restrict access to only what is needed.

### Monitor

- **Option A**: Cloudflare's Analytics tab shows you traffic. Check it occasionally for anything weird.
- **Option B**: your VPS provider's monitoring + your nginx access logs. Same idea.

---

## On Starlink Specifically

Starlink uses carrier-grade NAT (CGNAT) which means you do not get a static public IP and cannot port-forward directly. Both options here handle that:

- **Option A**: the Pi opens an outbound tunnel — CGNAT can't block outbound connections.
- **Option B**: same — both the Pi and the VPS open outbound Tailscale connections; the VPS just happens to also have its own public IP for the world to reach.

This works on any CGNAT'd ISP, not just Starlink.

---

## You Can Always Go Back

If any of this feels wrong, too complex, or like you've exposed something you didn't mean to — stop. Your data on the Pi is unaffected.

**Option A**: in the Cloudflare dashboard, go to your tunnel and click **Delete**. The DNS record disappears. cloudflared keeps running but has nowhere to route. Stop it with `sudo systemctl stop cloudflared` if you want it gone entirely.

**Option B**: stop nginx on the VPS:

```bash
sudo systemctl stop nginx
```

Done. You're local only again either way.

---

## Auto-Sync from Apple Health

You don't have to type biometrics in by hand. Two options, pick the one that fits.

### Option A: sardinessync native iOS app (recommended if you have a Mac)

**[sardinessync](https://github.com/alaricmoore/sardinessync)** is a native SwiftUI companion app that reads HealthKit on your iPhone, computes RMSSD on-device from raw RR intervals, and POSTs the result to your sardine-track instance. It's in its own repo because the iOS code and the Flask code evolve on different cadences.

**Why this and not the App Store?** It's not in the App Store. I don't pay Apple $99 a year to list a tool that runs on my own server, talks only to my own server, and has one user. You build it yourself in Xcode.

**What you need:** a Mac with Xcode installed, and an Apple ID. No developer account required.

**Free-signing reality:** with a free personal Apple ID, builds work but the cert expires every 7 days — you plug the phone back into Xcode and hit build-run again, about 2 minutes. If you pay Apple $99/year, builds last a year. I free-sign; weekly rebuild is an annoyance, not a blocker.

**What it syncs that the Shortcut route can't:**

- **RMSSD** — requires raw RR interval data, which Apple doesn't expose to Shortcuts. The native app reads it and computes RMSSD on-device during an overnight window (10pm-8am).
- **Time in Daylight** (sun exposure minutes) — Apple tracks this on the watch but hides it from Shortcuts.
- **Respiratory rate** and **SpO2** — same story.

Full walkthrough in the sardinessync repo's README. Short version:

1. Clone the repo on your Mac
2. Open the `.xcodeproj` in Xcode
3. In **Signing & Capabilities**, set Team to your personal Apple ID and change the bundle identifier to something unique (e.g. `com.yourname.sardinessync`)
4. Plug in your iPhone (not the Simulator — HealthKit only works on real devices)
5. Hit build; trust the dev cert on the phone (Settings → General → VPN & Device Management)
6. In the app, set the server URL (`https://your-sardinetrack-instance/api/health-sync`) and the bearer token from your `config.json`
7. Grant HealthKit permissions
8. "Sync Now" should report `synced N fields: steps, hrv, rmssd, ...`

It then runs automatically in the background overnight. Flare alerts and medication dose reminders arrive as local push notifications.

**Xcode sucks. Hard.** If you're reading this after the third "Command failed due to signal: Segmentation fault: 11" — I'm sorry, we've all been there.

### Option B: iOS Shortcut (no Mac required)

Good fallback if you don't have a Mac or don't want to touch Xcode. This uses the built-in Shortcuts app, no code.

**What it syncs:** steps, HRV (SDNN, not RMSSD), resting heart rate, and basal body temperature (delta).

**What it doesn't sync:** RMSSD (requires raw RR intervals — native-app-only), sleep (enter manually — Apple Health struggles with polyphasic sleep and sleepwalking), sun exposure minutes (Apple doesn't expose Time in Daylight to Shortcuts despite tracking it on the watch), respiratory rate, SpO2, and period flow (use sardine-track directly — it's better at cycle tracking than Apple Health anyway).

### Setup

Your sardine-track instance has an API endpoint at `/api/health-sync` that accepts health data via a secure token. The token is in your `config.json` file on the Pi (generated when you run `setup.py`). Treat this token like a password.

### Building the Shortcut

Open the **Shortcuts** app on your iPhone and create a new shortcut:

**1. Get today's date**
- Add a **Date** action
- Add a **Format Date** action, set format to **Custom**: `yyyy-MM-dd`

**2. Pull health data**

Add four **Find Health Samples** actions, one for each metric:

| Action | Sample Type | Sort By | Limit |
|--------|------------|---------|-------|
| 1 | Step Count | Start Date, Most Recent | 1 |
| 2 | Heart Rate Variability | Start Date, Most Recent | 1 |
| 3 | Resting Heart Rate | Start Date, Most Recent | 1 |
| 4 | Body Temperature | Start Date, Most Recent | 1 |

For Step Count, make sure you're getting the **sum for the day**, not just the most recent sample.

**3. Build the request**

Add a **Dictionary** action with these keys:

| Key | Type | Value |
|-----|------|-------|
| user_id | Number | Your user ID (usually 1) |
| date | Text | *select the Formatted Date from step 1* |
| steps | Number | *select result from step 2, action 1* |
| hrv | Number | *select result from step 2, action 2* |
| resting_heart_rate | Number | *select result from step 2, action 3* |
| basal_temp_delta | Number | *select result from step 2, action 4* |

**4. Send it**

Add a **Get Contents of URL** action:
- URL: `https://your-sardinetrack-instance/api/health-sync`
- Method: **POST**
- Headers:
  - `Authorization`: `Bearer YOUR_TOKEN_HERE`
  - `Content-Type`: `application/json`
- Request Body: **JSON** — select the Dictionary from step 3

**5. Test it**

Tap the play button to run the shortcut. You should see a response like `{"ok": true, "fields_updated": ["steps", "hrv", ...]}`. Check your sardine-track daily entry to confirm the values appeared.

**6. Automate it**

Go to the **Automation** tab in the Shortcuts app:
- Tap **+**, choose a trigger:
  - **"Bedtime begins"** — syncs when your wind-down starts (recommended)
  - **"Time of Day"** — set to 11:50 PM daily
- Set to **Run Immediately** so it doesn't ask for confirmation
- Select your Health Sync shortcut

Once set up, your phone will quietly sync your health data every night without you lifting a finger. On bad days, that's one less thing to worry about.

### Security Note

The API token in your Shortcut has write access to your health data. It can only write a limited set of biometric fields (steps, HRV, heart rate, temperature, sun minutes) and cannot touch symptoms, flare status, medications, or notes. But still — don't share your Shortcut with anyone unless you trust them with your sardine-track login.

---

## Final Note

This guide describes two specific setups, both of which the author has actually run. There are other valid patterns (WireGuard direct, ZeroTier, Headscale, plain VPN, etc.) and what's documented here is not the only way. Security is not a product, it's a practice. The threat model for your health data is yours to assess.

If you are a domestic violence survivor, a person in an unsafe living situation, or someone whose health data could be used against them in any context — think carefully before putting any of this on the internet in any form. Local only may be the right choice permanently.

Take care of your data the way you take care of yourself. Carefully, with attention, and with the understanding that you are worth protecting.

---

*This document is provided for informational purposes only. The author is not responsible for security outcomes resulting from network configuration choices made by users of this software.*
