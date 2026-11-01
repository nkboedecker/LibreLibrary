# Getting started

LibreLibrary has no release yet. These steps work from a checkout of the repository, and they cover the REST API only, because the web interface doesn't exist yet.

## Run the server

Build and start the image:

```sh
docker build --tag librelibrary:dev .
docker run --detach --name librelibrary --publish 8000:8000 \
    --volume librelibrary-data:/data librelibrary:dev
```

The server applies database migrations when it starts, and stops if a migration fails. Back up the data volume before you upgrade.

## Create the first admin

Run this command once. It prompts for a password of at least 12 characters:

```sh
docker exec --interactive --tty librelibrary \
    librelibrary create-admin --username admin
```

## Sign in

Sign in to get a bearer token, and send that token with each request:

```sh
curl --request POST http://localhost:8000/api/v1/auth/login \
    --header "Content-Type: application/json" \
    --data '{"username": "admin", "password": "YOUR_PASSWORD"}'

curl http://localhost:8000/api/v1/users/me \
    --header "Authorization: Bearer YOUR_TOKEN"
```

A sign-in token has the `library:read` and `library:write` scopes and lasts 30 days. To administer the instance, request the `admin` scope by adding `"scopes": ["admin"]` to the sign-in request.

The token is shown only once. You can list and revoke your tokens at `/api/v1/tokens`.

## Settings

Set these environment variables to configure the server:

| Variable | Default | Purpose |
|---|---|---|
| `LIBRELIBRARY_DATABASE_URL` | `sqlite:////data/librelibrary.db` in the image | The database. For PostgreSQL, use `postgresql+pg8000://USER:PASSWORD@HOST/NAME`. |
| `LIBRELIBRARY_LOCAL_AUTH_ENABLED` | `true` | Set to `false` to turn off password sign-in. |
| `LIBRELIBRARY_LOGIN_RATE_LIMIT_PER_IP` | `20/minute` | Sign-in attempts allowed from one address. |
| `LIBRELIBRARY_LOGIN_RATE_LIMIT_PER_USERNAME` | `10/minute` | Sign-in and password-change attempts allowed for one username. |
| `LIBRELIBRARY_LOGIN_TOKEN_LIFETIME_DAYS` | `30` | How long a sign-in token lasts. |
| `LIBRELIBRARY_TRUSTED_PROXIES` | `[]` | A JSON list of proxy addresses or networks, such as `["192.0.2.0/24"]`. `X-Forwarded-For` and `X-Forwarded-Proto` are read only from these. |

If you run the server behind a reverse proxy, set `LIBRELIBRARY_TRUSTED_PROXIES`. Otherwise, all clients share one sign-in limit, because they all appear to come from the proxy, and redirects point at `http://` instead of `https://`.

## API reference

The API is described by the generated specification in `openapi/openapi.json`. The server doesn't serve this file or interactive docs, because the only public route is `/api/v1/health`.
