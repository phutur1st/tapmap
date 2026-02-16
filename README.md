# TapMap

**See who your computer is talking to, on a live world map.**

TapMap shows your active network connections and where they are located.  
It is fast, simple and runs entirely on your own machine.

TapMap is not a firewall or a full security suite.  
Think of it as a network thermometer for a quick overview.

---

## Screenshot

![TapMap main view](docs/screenshot.png)

---

## Download

Download the latest version from the Releases page:

https://github.com/olalie/tapmap/releases

Available builds:

- Windows (zip)
- macOS (zip)
- Linux (zip)

No installation required. Download, extract and run.

---

## Windows SmartScreen

Windows may show a SmartScreen warning the first time you run TapMap.  
This is normal for new applications that are not digitally signed.

To start the program:

1. Click **More info**.
2. Click **Run anyway**.

TapMap runs locally and does not install anything on your system.

---

## How it runs

TapMap runs locally and opens in your browser.

If it does not open automatically, go to:
http://127.0.0.1:8050/

---

## GeoIP databases (required)

TapMap uses local MaxMind GeoLite2 databases for geolocation.  
The databases are not included in the download.

TapMap can run without them, but geolocation will be disabled.

Required files:

- GeoLite2-City.mmdb
- GeoLite2-ASN.mmdb

Download is free from MaxMind, but requires an account and acceptance of license terms:

https://dev.maxmind.com/geoip/geolite2-free-geolocation-data

### If you use the prebuilt release

1. Extract the downloaded zip file.
2. Place the `.mmdb` files in the `data` folder next to the TapMap executable.

### If you run TapMap from source with Python

Place the `.mmdb` files in the folder defined by `GEO_DATA_DIR` in `config.py`.

Update recommendation: download updated databases regularly (for example monthly).  
Redistribution rules depend on the MaxMind license terms.

---

## Interface

### Actions menu
![Actions menu](docs/menu.png)

### Unmapped endpoints
![Unmapped endpoints](docs/unmapped.png)

### Open ports
![Open ports](docs/openports.png)

### About TapMap
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
| H | Help |
| A | About |
| ESC | Close window |

---

## Privacy

- TapMap runs locally.
- No connection data is sent anywhere.
- Geolocation uses local MaxMind databases.
- If `MY_LOCATION = "auto"`, TapMap makes a single request to detect your public IP.
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

    pip install -r requirements.txt

Run:

    python tapmap.py

---

## License

MIT License
