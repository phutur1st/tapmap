from dash import html

HELP_CONTENT = [
    html.H1("Help"),

    html.H2("Overview"),
    html.P("TapMap shows which remote systems your computer is currently connected to, and where they are located."),
    html.P("Hover markers for a summary. Click markers for details."),
    html.P("Use mouse or Plotly tools (top right) to pan, zoom and reset view."),

    html.H2("Map legend"),
    html.Ul([
        html.Li([html.Span("Magenta", style={"color": "magenta", "fontSize": "larger"}),
                 " markers and lines show normal remote connections."]),
        html.Li([html.Span("Yellow", style={"color": "yellow", "fontSize": "larger"}),
                 " markers and lines indicate nearby locations."]),
        html.Li([html.Span("Cyan", style={"color": "cyan", "fontSize": "larger"}),
                 " marker shows your location (if enabled)."]),
    ]),
    html.P("Yellow is a visual hint only. Zoom in or approach the cluster from another direction to separate nearby endpoints."),
    html.P("Location grouping is a separate mechanism where endpoints with the same rounded coordinates are shown as a single map marker."),

    html.H2("Controls"),
    html.Table(
        className="mx-table mx-help-controls",
        children=[
            html.Thead(
                html.Tr([
                    html.Th("Key"),
                    html.Th("Action"),
                ])
            ),
            html.Tbody([
                html.Tr([html.Td("U"),   html.Td("Show unmapped endpoints (missing geolocation)")]),
                html.Tr([html.Td("O"),   html.Td("Show open ports (TCP LISTEN and UDP bound)")]),
                html.Tr([html.Td("T"),   html.Td("Show cache in terminal")]),
                html.Tr([html.Td("C"),   html.Td("Clear cache")]),
                html.Tr([html.Td("H"),   html.Td("Help")]),
                html.Tr([html.Td("A"),   html.Td("About")]),
                html.Tr([html.Td("ESC"), html.Td("Close this window")]),
            ]),
        ],
    ),

    html.H2("Unmapped endpoints"),
    html.P("Unmapped endpoints lists ESTABLISHED TCP connections not shown on the map because geolocation (lat/lon) is missing."),
    html.P("By default, only PUBLIC endpoints are shown. You can enable the toggle to include LAN and LOCAL endpoints."),
    html.P("Some fields may be truncated if the window is narrow. Hover a table cell to see the full value as a tooltip."),

    html.H2("Open ports"),
    html.P("Open ports lists local TCP sockets in LISTEN state and UDP sockets bound to a local port."),
    html.P("TCP LISTEN means a local process is waiting for incoming connections. UDP bound means a local process can receive UDP datagrams on that port."),
    html.P("It is a local view only. It does not show remote endpoints."),
    html.P("Some fields may be truncated if the window is narrow. Hover a table cell to see the full value as a tooltip."),

    html.H2("Show cache in terminal"),
    html.P("Prints the current cache contents to the terminal window where TapMap is running."),


    html.H2("Status line"),
    html.P("A snapshot is a point in time view of your current network connections."),
    html.H3("STATUS: WAIT | OK | OFFLINE | ERROR"),
    html.Ul([
        html.Li("WAIT: No snapshot received yet."),
        html.Li("OK: Snapshot received successfully."),
        html.Li("OFFLINE: Snapshot received, but no internet connectivity detected."),
        html.Li("ERROR: Model failed to fetch or enrich data. See terminal."),
    ]),

    html.H3("LIVE"),
    html.P("Shows the current snapshot."),
    html.Ul([
        html.Li("CON: Total TCP entries (all states)."),
        html.Li("EST: Connections in state ESTABLISHED."),
        html.Li("LST: Listening TCP sockets on the local machine."),
    ]),
    html.P("CON includes all TCP states (not only ESTABLISHED and LISTEN), for example TIME_WAIT, SYN_SENT and CLOSE_WAIT."),


    html.H3("CACHE"),
    html.P("Aggregated information since the last Clear cache or app start."),
    html.P("Only ESTABLISHED connections with a remote endpoint are included."),
    html.P("Format: EST - LOC - NON_GEO = GEO -> RIP -> RLOC"),

    html.Ul([
        html.Li("EST: Unique remote endpoints seen in ESTABLISHED connections (remote IP + port)."),
        html.Li("LOC: Endpoints where the remote IP is local, private or loopback (not shown on the map)."),
        html.Li("NON_GEO: External endpoints without geolocation (not shown on the map, but available via menu U)."),
        html.Li("GEO: External endpoints with valid geolocation (GEO = EST - LOC - NON_GEO)."),
        html.Li("RIP: Unique remote IP addresses within GEO."),
        html.Li("RLOC: Map locations within GEO after coordinate grouping. Multiple IPs and network operators (ASN) may map to the same grouped location."),
    ]),

    html.H3("UPDATED"),
    html.P("Time of the last snapshot."),

    html.H3("MYLOC: FIXED | AUTO | AUTO (NO GEO) | OFF"),
    html.P("Shows your local map location based on the MY_LOCATION setting in config.py."),
    html.Ul([
        html.Li("FIXED: Uses the fixed coordinates from config.py."),
        html.Li("AUTO: Location detected from your public IP."),
        html.Li("AUTO (NO GEO): Public IP detected, but no geolocation available."),
        html.Li("OFF: Local marker and connection lines are hidden."),
    ]),

    html.H2("Network and location notes"),
    html.Ul([
        html.Li("Location is based on IP geolocation and is approximate."),
        html.Li("ASN and ASN org identify the network operator, not necessarily the service owner."),
        html.Li("CDNs and hosting can make a service appear in another country."),
        html.Li("VPN and Tor can hide the true origin of the remote endpoint."),
    ]),

    html.H2("GeoIP databases (MaxMind GeoLite2)"),
    html.P("TapMap uses local MaxMind mmdb files for geolocation. The databases are not included."),
    html.P("Required files:"),
    html.Ul([
        html.Li("GeoLite2-City.mmdb"),
        html.Li("GeoLite2-ASN.mmdb"),
    ]),
    html.P("By default, place the files in a folder named 'data' next to the TapMap program."),
    html.P([
        "Download is free from MaxMind, but requires an account and acceptance of license terms. ",
        "Create a free account and download the databases here: ",
        html.A(
            "MaxMind GeoLite2 download page",
            href="https://dev.maxmind.com/geoip/geolite2-free-geolocation-data",
            target="_blank"
        ),
        "."
    ]),
    html.P("Update recommendation: download updated databases regularly (for example monthly)."),
    html.P("Redistribution rules depend on MaxMind license terms."),

    html.H2("Configuration (config.py)"),
    html.P("TapMap reads settings from config.py. Python users can edit this file to adjust behaviour."),
    html.P("Common settings:"),
    html.Ul([
        html.Li("MY_LOCATION: 'none' hides the local marker. Use (lon, lat) for a fixed marker, or 'auto' to place it based on your public IP."),
        html.Li("POLL_INTERVAL_MS: Snapshot refresh interval (milliseconds)."),
        html.Li("COORD_PRECISION: Decimal precision used to group endpoints into one map marker (3 ≈ 100 m)."),
        html.Li("ZOOM_NEAR_KM: Distance threshold for marking endpoints as nearby (yellow)."),
    ]),

    html.H2("Privacy and safety"),
    html.P("TapMap runs locally and reads local network connections."),
    html.P("Geolocation lookups are performed locally using the mmdb files."),
    html.P("If MY_LOCATION is set to 'auto', TapMap makes a single request to api.ipify.org to determine the public IP address."),
    html.P("To detect OFFLINE status, TapMap performs short connection checks to the public DNS servers 1.1.1.1 and 8.8.8.8."),
]
