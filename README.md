# Ping Tuckz

Ping Tuckz is a small network monitor. It repeatedly pings an IP address or hostname, watches for slow replies or timeouts, and saves the results so you can review connection problems later.

By default it pings Google's DNS server, `8.8.8.8`. You can also give it another target, such as your router, modem, game server, or another DNS server.

## How to Run

On Windows, use the batch file:

```bat
run.bat
```

That starts monitoring `8.8.8.8`.

To ping something else, put the IP address or hostname after `run.bat`:

```bat
run.bat 1.1.1.1
run.bat 192.168.1.1
run.bat example.com
```

Press `Ctrl+C` to stop. When it stops, the tool finishes writing the report files.

## What It Shows

The live console output marks each reply as:

- `NORMAL`: under 50 ms
- `MEDIUM`: 50 to 100 ms
- `HIGH`: over 100 ms
- `TIMEOUT`: no reply

The tool groups slow replies and timeouts into events so short problem periods are easier to spot.

## Output Files

Results are saved in the `Results` folder. The tool creates one text file and one HTML report per day, named by date, such as `2026-02-13.txt` and `2026-02-13.html`.

Open the HTML file in a browser to review the day's connection history, summaries, event chunks, and latency graph.

## Privacy

Ping Tuckz stores results locally. Result files record timestamps, latency values, and timeout events; they do not store raw ping output, target hostnames, reply IP addresses, usernames, environment variables, or system paths.

Review result files before sharing them, because timestamps can still reveal when monitoring was running.

## Direct Python Use

You can also run the script directly:

```bat
python ping-tuckz.py
python ping-tuckz.py 1.1.1.1
```

## Dependencies

Ping Tuckz uses only Python standard library modules. It has no third-party package dependencies.

## Contributions

This is a personal project shared for others to use or fork. Pull requests, feature requests, and support requests are not being accepted.

You are welcome to fork the project and modify it for your own needs under the terms of the MIT License.
