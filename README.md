# Torch Hosting 
Plugins and utilities for Space Engineers Torch server hosting.

## Hosting

Torch plugin useful for server hosting and maintenance.

### Features
- Writes the current timestamp in ISO standard format into the **Instance/canary** file once every 20 seconds. Useful to detect if the instance is frozen.
- Writes the Torch process's PID into the **Instance/pid** file once the session is loaded. Useful to identify the process corresponding to a given instance folder.

## Utilities

### blueprint_downloader.py

Downloads blueprints from Steam or direct `bp.sbc` URLs (like Discord file links or GitHub).

- Monitors a folder for download requests (URLs in files)
- Executes the downloads requested, removes the request files at the same time
- Puts the downloaded blueprint bp.sbc file into a cache folders with the same filename as the request
- Periodically cleans old downloads from the cache folder
- Removes nested blueprints deeper than MAX_PROJECTION_DEPTH

It should be executed in the background. Running multiple processes at the same time is supported.

It is used for the racing maps to download cars and the Moon Ring world of the Space Battle server.

## Linux

### prepare-debian-10.sh

Prepares a Debian 10 server to run Torch instances. First run this script as root only once.

### prepare-user.sh

Prepares a specific user to run Torch instances.

Creates the `.wine00` and `.ds00` template folders under the user's home. These are used by the `server.py` hosting script to rapidly initialize new Torch instances.

To upgrade Torch please delete the `~/.ds00` folder, then re-run the `prepare-user.sh` as root to re-initialzie the template.

### server.py

Controls Torch instances under a prepared user.

#### Help
```bash
./server.py --help
./server.py create --help
./server.py start --help
./server.py kill --help
./server.py archive --help
./server.py destroy --help
```

#### Examples
```bash
./server.py create 16 moon-ring.zip
./server.py start 16
./server.py list
./server.py status 16
./server.py check 16
./server.py kill 16
./server.py destroy 16
./server.py archive 16
```

#### Notes
- **Destroy kills and DELETES the server!**
- This is a "raw" hosting command and does not ask twice, so be careful.
- Server NN is on port 270NN, so 16 will be served on port 27016.
- The create command clones the .wine00 and ds00 into the given number (like 16) and prepares the world from the ZIP into that server. It does not start Torch.
- The start command starts the prepared Torch server.
- You can use the archive command to delete a server while saving the world and logs for later, they go into the ~/archive folder.
- There is also a keepalive command to periodically check on a server and restart as needed.

#### Log files
```bash
tail -f ~/ds16/Logs/Keen-2021-02-06.log
tail -f ~/ds16/Logs/Torch-2021-02-06.log
```
The date in the filename will change with time.
