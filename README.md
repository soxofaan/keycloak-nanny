
# Keycloak Nanny

Simple Python wrapper around the Keycloak admin REST API,
to programmatically create realms, clients, users, ...

Intended to be used on test/toy/dummy Keycloak instances,
e.g. running locally in docker:

```bash
docker run --rm \
    -p 8642:8080 \
    -e KEYCLOAK_ADMIN=admin \
    -e KEYCLOAK_ADMIN_PASSWORD=admin \
    quay.io/keycloak/keycloak:21.0.2 start-dev
```
