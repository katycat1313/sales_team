# Mac App — Agent Command

This wraps the dashboard in a native Mac app with:
- Sits in your dock
- Menu bar tray icon with approval count
- Desktop notifications when agents need approval
- Connects to G14 via Tailscale

## Setup (one time)

1. Install Node.js if you don't have it: https://nodejs.org
2. Open Terminal, navigate to this folder:
   ```bash
   cd /path/to/agent_team/mac_app
   ```
3. Install dependencies:
   ```bash
   npm install
   ```
4. Set your G14's Tailscale IP:
   - Open main.js
   - Change `100.x.x.x` to your G14's actual Tailscale IP
   - (You'll get this IP after setting up Tailscale on the G14)

5. Run the app:
   ```bash
   npm start
   ```

## To build a proper .app you can double-click
```bash
npm run build
```
This creates a .dmg in the dist/ folder you can install like any Mac app.

## Daily use
Just run `npm start` from this folder, or drag the built .app to your Applications folder.
The app connects to your G14 over Tailscale — works from anywhere.
