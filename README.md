# RPipe
A little python remote pipe server and client.

# Install

`pip install rpipe`

# Usage

Before anything else, you should set your pipe server URL and default channel (the default channel can be any string)
```bash
rpipe --url <url> -c <channel> --save_config
```

### Sending
```bash
echo "abc" | rpipe
```

### Receiving
```bash
rpipe
```

### Custom URL or channel
Both sending and receiving support the command line options `-c`/`--channel` and `-u`/`--url` to use a different channel or url than is saved.


# Server

Start the server via:
```bash
rpipe_server <port>
```
