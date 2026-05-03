# webapp-210401210447

## Run locally for iPad testing

Start the app with:

```sh
./run-local-ipad.sh
```

The script starts Jetty on port `8080` and prints two URLs:

- `http://localhost:8080/` for the computer running the script
- `http://<local-ip>:8080/` for an iPad on the same Wi-Fi network

To use a different port:

```sh
PORT=9090 ./run-local-ipad.sh
```

Keep the terminal open while testing. Press `Ctrl+C` to stop the server.