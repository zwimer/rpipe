# RPipe
A little python remote pipe server and client.

# Install

`pip install rpipe`

# Usage

Before anything else, you should set your pipe server URL and default channel (the default channel can be any string)
```bash
RPIPE_PASSWORD="my password"  # Only need to set when saving config
rpipe --url <url> -c <channel> --password-env --save_config
```

If no password is desired, use `--no-password`; though data will be uploaded without encryption if this is done.

### Sending
```bash
echo "abc" | rpipe
```

### Receiving
```bash
rpipe        # Read the data
rpipe -c foo # Read data from the channel "foo"
rpipe --peek # Read the data but do not remove it from the server
```

Additional options can be found via `rpipe --help`

### Custom URL or channel
Both sending and receiving support the command line options `-c`/`--channel` and `-u`/`--url` to use a different channel or url than is saved.


# Server

Start the server via:
```bash
rpipe_server <port> [--host <host>] [--debug]
```
