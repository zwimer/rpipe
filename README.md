# rpipe
A little python remote pipe server and client.

# Install

`pip install rpipe`

# Usage

Before anything else, you should set your pipe server URL and default channel (the default channel can be any string)
```bash
export RPIPE_PASSWORD="my password"  # Only need to set when saving config
rpipe --url <url> -c <channel> --password-env --update-config
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

Additional options can be found via `rpipe --help`.
Note that peeking will only show the data presently available, it will not construct a persistent pipe like reading will.

### Web Version

While discouraged and lacking support for encryption, users can forgo usage of the `rpipe` client and connect directly to an `rpipe` with simple `GET`/`POST` requests.
Visit the server's URL `/help` for more details.

### Custom URL or channel
Both sending and receiving support the command line options `-c`/`--channel` and `-u`/`--url` to use a different channel or URL than is saved.


# Server

Start the server via:
```bash
rpipe_server <port> [--host <host>] [--debug]
```
