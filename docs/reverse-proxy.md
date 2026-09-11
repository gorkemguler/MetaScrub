# Putting MetaCLS behind a reverse proxy

The `metacls web` UI has **no authentication** and the `metacls api`
service only checks an API key. Both refuse to bind a non-loopback
address without `--api-key` (API) unless you pass `--insecure`. The
supported way to expose either one is: bind it to `127.0.0.1`, then put a
proxy in front that terminates TLS and authenticates the caller.

Run the app on loopback:

```bash
metacls web --host 127.0.0.1 --port 8770 --output-dir /srv/metacls
# or
metacls api --host 127.0.0.1 --port 8000 --output-dir /srv/metacls \
  --api-key "$(openssl rand -hex 24)" --run-ttl-days 30
```

Uploads can be large — raise the proxy's body-size limit to match
`--max-upload-mb` (API) or the web UI's 200 MB.

## Caddy

`Caddyfile` — automatic HTTPS, HTTP basic auth in front of the web UI:

```caddy
scrub.example.com {
    # bcrypt hash: caddy hash-password --plaintext 'your-password'
    basic_auth {
        alice $2a$14$....hash....
    }
    reverse_proxy 127.0.0.1:8770
    request_body {
        max_size 210MB
    }
}
```

For the **API**, callers already send `X-API-Key`, so you usually don't
add basic auth — just proxy and cap the body:

```caddy
scrub-api.example.com {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 210MB
    }
}
```

## nginx

```nginx
server {
    listen 443 ssl;
    server_name scrub.example.com;

    ssl_certificate     /etc/letsencrypt/live/scrub.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/scrub.example.com/privkey.pem;

    # web UI only — the API authenticates itself, drop this block for it.
    auth_basic           "MetaCLS";
    auth_basic_user_file /etc/nginx/metacls.htpasswd;   # htpasswd -c ... alice

    client_max_body_size 210m;

    location / {
        proxy_pass         http://127.0.0.1:8770;   # 8000 for the API
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;                    # big scrubs / big uploads
    }
}
```

## Docker

`docker-compose.yml` publishes both services on `127.0.0.1` already. Add
your proxy as another service on the same Docker network and point it at
`metacls:8770` / `metacls-api:8000` instead of `127.0.0.1`.

## Checklist

- App bound to `127.0.0.1` (or a private Docker network), never `0.0.0.0`
  on a public host without a proxy.
- TLS terminated at the proxy.
- Web UI: basic auth / SSO / an allow-listed network in front of it.
- API: `--api-key` set; the proxy can add basic auth too if you want a
  second factor.
- Proxy body-size limit ≥ the app's upload cap.
- `--run-ttl-days` set on the API so old runs and their files are pruned.
