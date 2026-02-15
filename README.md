# TapMap

**See who your computer is talking to, on a live world map.**

TapMap shows your active network connections and where they are located.  
It is fast, simple and runs entirely on your own machine.

TapMap is not a firewall or a full security suite.
Think of it as a network thermometer that gives you a quick first look.

---

## Download

Download the latest release:  
https://github.com/USERNAME/tapmap/releases

Available builds:

- Windows (exe)
- macOS
- Linux (Ubuntu)

No installation required. Download and run.

---

## How it runs

TapMap runs locally and opens in your browser.

If it does not open automatically, go to:
http://127.0.0.1:8050/

---

## Screenshot

![TapMap main view](docs/screenshot.png)

---

## Interface

### Actions menu
![Actions menu](docs/menu.png)

### Unmapped endpoints
![Unmapped endpoints](docs/unmapped.png)

### Open ports
![Open ports](docs/openports.png)

### My info
![My info](docs/myinfo.png)

---

## What TapMap shows

- Remote endpoints your computer is connected to
- Approximate locations on a world map
- Nearby clusters highlighted visually
- Unmapped endpoints with missing geolocation
- Local open ports

All data is collected locally on your machine.

---

## Why TapMap

Most computers communicate with dozens of remote systems every day.  
You usually cannot see them.

TapMap makes this visible in seconds.

- See unexpected connections
- Understand where traffic goes
- Get a quick health check of your system

If everything looks familiar, you are probably fine.  
If something looks strange, you can investigate further.

---

## Keyboard controls

| Key | Action |
|-----|--------|
| U | Unmapped endpoints |
| O | Open ports |
| T | Show cache in terminal |
| C | Clear cache |
| I | My info |
| H | Help |
| ESC | Close window |

---

## Privacy

- TapMap runs locally.
- No connection data is sent anywhere.
- Geolocation uses local MaxMind databases.
- If `MY_LOCATION = "auto"`, TapMap makes one request to detect your public IP.
- To detect offline status, TapMap performs short connection checks to the public DNS servers 1.1.1.1 and 8.8.8.8.

---

## Support the project

TapMap is free and open source.

⭐ If you like TapMap, please give it a star on GitHub.
It helps others discover the project.

If it helps you, consider supporting the project:

**Buy Me a Coffee**  
https://www.buymeacoffee.com/olalie  

**PayPal**  
https://www.paypal.com/donate/?hosted_button_id=ELLXBK9BY8EDU

Even small donations are appreciated.

---

## Configuration

TapMap reads settings from `config.py`.

Common settings:

- `MY_LOCATION`
- `POLL_INTERVAL_MS`
- `COORD_PRECISION`
- `ZOOM_NEAR_KM`
- `GEO_DATA_DIR`

---

## Build from source

Requirements:

- Python 3.10+

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python tapmap.py
```

---

## GeoIP databases (required)

TapMap uses MaxMind GeoLite2 databases.

Required files:

- `GeoLite2-City.mmdb`
- `GeoLite2-ASN.mmdb`

Steps:

1. Create a free account at MaxMind.
2. Download the GeoLite2 City and ASN databases.
3. Place the `.mmdb` files in the folder defined by `GEO_DATA_DIR` in `config.py`.

---

## License

MIT License
