## Konecty Python SDK

> 🛠️ Work in progress

This project exposes both:

- a cli for interacting with the database
- the Konecty client sdk for interacting with Konecty's api

#### Usage

##### Installing on a project

```sh
uv pip install konecty-sdk-python
konecty-cli apply --mongo-url="..." --database my-db
```

##### Running on uvx

```sh
uvx --from konecty-sdk-python konecty-cli pull --all --mongo-url="..." --database my-db
```

#### Build & Publish

It is needed to increase the version number on the [pyproject](./pyproject.toml) file.

```sh
uv build
uvx twine upload --config-file .pypirc --skip-existing dist/*
```
