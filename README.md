
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

Then create realms, client and users against this instance:

```python
kc_nanny = keycloaknanny.KeycloakNanny("http://localhost:8642"),


realm = nanny.create_realm()
print("Created realm", realm)
nanny.set_default_realm(realm.name)

client = nanny.create_client()
print("Created client", client)

user = nanny.create_user()
print("Created user", user)

```
